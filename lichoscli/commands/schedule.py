# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProjectFetchingError, ValidationError
from lichoscli.core.models.dag import DAGNodeStatus
from lichoscli.core.services import (
    StorageService,
    WorkspaceService,
)
from lichoscli.core.services.package import PackageService
from lichoscli.core.services.scheduler_service import SchedulerService
from lichoscli.ui.presenters.dag import dag_to_tree, version_check_summary
from lichoscli.ui.presenters.scheduler import SchedulerOutputListener
from lichoscli.utils.constants import CI_PKG

logger = logging.getLogger(__name__)


class ScheduleCommand(Command):
    """Schedule sequential builds for all packages in a workspace"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.workspace_service = di_container.obtain_ref(WorkspaceService)
        self.scheduler_service = di_container.obtain_ref(SchedulerService)
        self.package_service = di_container.obtain_ref(PackageService)
        self.previous_dag = di_container.obtain_ref(StorageService).load_workspace_state(
            self.args.branch
        )

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument(
            "--skip-version-check",
            action="store_true",
            help="Skip version check; build all packages",
        )
        sp.add_argument(
            "--poll-interval",
            type=int,
            default=10,
            help="Interval in seconds to check build status (default: 10)",
        )

    def execute(self) -> int:
        """Execute the schedule command"""
        workspace = self.workspace_service.get_workspace(self.args.branch)
        if not workspace:
            self.output.error("Error: Workspace '{0}' not found".format(self.args.branch))
            return 1

        self.output.accent("Scheduling builds for workspace '{0}' packages:".format(
            self.args.branch
        ))

        packages = [p for p in workspace.packages if p.name != CI_PKG]

        all_packages = self.package_service.get_all_packages()
        report = self.scheduler_service.analyze_reverse_dependencies(
            packages, all_packages, self.args.branch,
        )
        missing_dependencies = [entry.name for entry in report.missing]

        listener = SchedulerOutputListener(self.output)
        self.scheduler_service.await_running_pipelines(
            packages, self.args.branch, self.args.poll_interval, listener=listener,
        )

        cancelled = self.scheduler_service.cancel_orphan_pipelines(
            packages, self.args.branch
        )
        if cancelled:
            self.output.warning(
                "Cancelled {0} orphan pipeline(s): {1}".format(
                    len(cancelled), ", ".join(sorted(cancelled))
                )
            )

        analysis = self.scheduler_service.prepare_schedule(
            packages=packages,
            branch=self.args.branch,
            skip_version_check=self.args.skip_version_check,
            previous_dag=self.previous_dag,
        )

        dag = analysis.dag
        if not dag or not dag.nodes:
            self.output.error("Error: Could not build dependency DAG")
            return 1

        if analysis.skipped:
            self.output.warning("\nSkipping rebuild - {0}".format(analysis.skip_reason))
            return 0

        if self.args.skip_version_check:
            self.output.warning("Warning: Skipping version checking - building all packages")
            self.output.accent(
                "\nBuilding dependency DAG for analysis...\n"
                "Dependency Analysis - {0} packages:".format(len(dag.nodes))
            )
        else:
            mismatch_results = [r for r in analysis.version_check_results if not r.is_correct]
            msg, style = version_check_summary(mismatch_results)
            getattr(self.output, style)(msg)

            if analysis.packages_needing_rebuild:
                total_packages = len([
                    n for n in dag.nodes.values() if n.project
                ])
                self.output.print(
                    "\nPackages needing rebuild: {0} of {1}".format(
                        len(analysis.packages_needing_rebuild), total_packages
                    )
                )
            else:
                self.output.success(
                    "\nAll packages have correct dependency versions and no failed pipelines!"
                )

            self.output.accent("Dependency Analysis - {0} packages:".format(len(dag.nodes)))

        self.output.tree(dag_to_tree(dag))

        pending_nodes = dag.get_nodes_by_status(DAGNodeStatus.PENDING)
        if not pending_nodes:
            self.output.success("All packages are up to date! No builds needed.")
            self.scheduler_service.post_dag_statuses(
                dag, workspace, scheduling_complete=True,
                missing_dependencies=missing_dependencies,
            )
            self.scheduler_service.send_build_notification(
                dag, workspace, self.previous_dag
            )
            self.scheduler_service.persist_state(workspace, dag)
            self.output.success("Persisted current DAG state")
            return 0

        if self.args.dry:
            self.output.print("\nDry run completed - no builds were triggered")
            if not self.args.skip_version_check and pending_nodes:
                self.output.warning(
                    "With version checking enabled, only packages with "
                    "dependency mismatches would be built"
                )
            return 0

        try:
            self.scheduler_service.post_dag_statuses(dag, workspace)
            result = self.scheduler_service.execute_schedule(
                dag=dag,
                workspace=workspace,
                poll_interval=self.args.poll_interval,
                listener=listener,
            )
        except (ProjectFetchingError, ValidationError) as e:
            logger.error("Error in schedule command: %s", str(e))
            self.output.error("Error: {0}".format(str(e)))
            return 1

        self.scheduler_service.post_dag_statuses(
            dag, workspace, scheduling_complete=True,
            missing_dependencies=missing_dependencies,
        )

        self.output.accent("\nBuild scheduling completed:")
        self.output.success("  Successfully triggered: {0}".format(result.total_builds))
        if result.failed_builds:
            self.output.error("  Failed: {0}".format(result.failed_builds))
        if result.blocked_packages:
            self.output.warning(
                "  Skipped (dependency failed): {0}".format(
                    ", ".join(result.blocked_packages)
                )
            )
        if missing_dependencies:
            self.output.warning(
                "Build dependencies not in workspace: {0}".format(
                    ", ".join(sorted(missing_dependencies))
                )
            )

        self.scheduler_service.send_build_notification(
            dag, workspace, self.previous_dag
        )
        self.scheduler_service.persist_state(workspace, dag)

        return 0
