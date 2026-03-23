# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import time

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProjectFetchingError, ValidationError
from lichoscli.core.models.dag import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.core.services import (
    DependencyService,
    NotifyService,
    PackageService,
    StorageService,
    WorkspaceService,
)
from lichoscli.core.services.notify import NotificationData
from lichoscli.ui.presenters.dag import dag_to_tree, version_check_summary

logger = logging.getLogger(__name__)


class ScheduleCommand(Command):
    """Schedule sequential builds for all packages in a workspace"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.workspace_service = di_container.obtain_ref(WorkspaceService)
        self.dependency_service = di_container.obtain_ref(DependencyService)

        self.storage_service = di_container.obtain_ref(StorageService)
        self.notify_service = di_container.obtain_ref(NotifyService)
        self.previous_dag = self.storage_service.load_workspace_state(self.args.branch)

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
        # TODO: remove this after deleting it from 00ci
        sp.add_argument(
            "--persist",
            action="store_true",
            help="Enable state persistence using storage service",
        )

    def execute(self) -> int:
        """Execute the schedule command"""
        workspace = self.workspace_service.get_workspace(self.args.branch)
        if not workspace:
            self.output.error(f"Error: Workspace '{self.args.branch}' not found")
            return 1

        if not workspace.packages:
            self.output.print(f"No packages found in workspace '{self.args.branch}'")
            return 0

        self.output.accent(f"Scheduling builds for workspace '{self.args.branch}' packages:")

        current_dag: DependencyGraph = self.dependency_service.build_dependency_dag(
            workspace.packages, self.args.branch
        )
        if not current_dag:
            self.output.error("Error: Could not build dependency DAG")
            return 1

        if self.previous_dag and not self.args.skip_version_check:
            if not self.dependency_service.has_dag_state_changed(self.previous_dag, current_dag):
                self.output.warning(
                    "\nSkipping rebuild - no changes to build graph state since last run",
                )
                return 0

        if self.args.skip_version_check:
            self.output.warning("Warning: Skipping version checking - building all packages")
            self.output.accent(
                "\nBuilding dependency DAG for analysis...\nDependency Analysis - {0} packages:".format(len(current_dag.nodes)),
            )
            self.output.tree(dag_to_tree(current_dag))
            for node in current_dag.nodes.values():
                node.set_status(DAGNodeStatus.PENDING)
        else:
            self._prepare_rebuild_schedule(current_dag)

        try:
            pending_nodes = current_dag.get_nodes_by_status(DAGNodeStatus.PENDING)
            if not pending_nodes:
                self.output.success("All packages are up to date! No builds needed.")

                if self.notify_service:
                    self._send_build_notification(current_dag)

                self.storage_service.save_workspace_state(self.args.branch, current_dag)
                self.output.success("Persisted current DAG state")

                return 0

            if self.args.dry:
                self.output.print("\nDry run completed - no builds were triggered")
                if not self.args.skip_version_check and pending_nodes:
                    self.output.warning(
                        "With version checking enabled, only packages with dependency mismatches would be built",
                    )
                return 0

            return self._execute_build_schedule(current_dag)

        except (ProjectFetchingError, ValidationError) as e:
            logger.error("Error in schedule command: %s", str(e))
            self.output.error(f"Error: {str(e)}")
            return 1

    def _prepare_rebuild_schedule(self, dag: DependencyGraph) -> None:
        """
        Analyse dependency versions and pipeline statuses, then mark the DAG
        for scheduling.  Packages that don't need rebuilding are set to SUCCESS;
        packages requiring a rebuild (plus their transitive dependents) stay
        PENDING for the scheduler to pick up.
        """
        self.output.accent("\nAnalyzing package dependencies and versions...")

        if not dag or not dag.nodes:
            logger.warning("Invalid DAG provided, cannot proceed with scheduling")
            return

        packages_needing_rebuild: set[str] = set()

        self.output.accent("\nChecking for packages with failed pipelines...")
        for package_name, node in dag.nodes.items():
            if node.status == DAGNodeStatus.FAILED:
                packages_needing_rebuild.add(package_name)

        if packages_needing_rebuild:
            self.output.warning(
                f"Found {len(packages_needing_rebuild)} packages with failed pipelines:",
            )

        all_version_check_results = self.dependency_service.check_all_dependency_versions_from_dag(
            dag
        )

        for result in all_version_check_results:
            if not result.is_correct:
                packages_needing_rebuild.add(result.dependent_package)
                logger.info(
                    "Version mismatch: %s built with %s v%s, but %s v%s is now available",
                    result.dependent_package,
                    result.binary_package,
                    result.used_version,
                    result.source_package,
                    result.expected_version,
                )

        dag.apply_version_check_results(all_version_check_results)

        mismatch_results = [r for r in all_version_check_results if not r.is_correct]
        msg, style = version_check_summary(mismatch_results)
        getattr(self.output, style)(msg)

        self.output.accent("Dependency Analysis - {0} packages:".format(len(dag.nodes)))
        self.output.tree(dag_to_tree(dag))

        initial_rebuild_packages = packages_needing_rebuild.copy()
        for package_name in initial_rebuild_packages:
            transitive_dependents = dag.get_transitive_dependents(package_name)
            packages_needing_rebuild.update(node.package for node in transitive_dependents)

        # Mark packages needing rebuild as PENDING, rest as SUCCESS
        for package_name, node in dag.nodes.items():
            if package_name in packages_needing_rebuild:
                node.set_status(DAGNodeStatus.PENDING)
            else:
                node.set_status(DAGNodeStatus.SUCCESS)

        if not packages_needing_rebuild:
            self.output.success(
                "\nAll packages have correct dependency versions and no failed pipelines!",
            )
            return

        total_packages = len([node.project for node in dag.nodes.values() if node.project])
        self.output.print(f"\nPackages needing rebuild: {len(packages_needing_rebuild)} of {total_packages}")

    def _execute_build_schedule(self, dag: DependencyGraph) -> int:
        """Execute builds using DAG-native scheduling for maximum parallelism. """
        total_builds = 0
        failed_builds = 0

        while True:
            ready_nodes = dag.get_ready_nodes()

            if ready_nodes:
                self.output.accent(
                    f"\nTriggering {len(ready_nodes)} ready packages...",
                )
                for node in ready_nodes:
                    dag.mark_building(node.package)
                    self.output.print(
                        f"  Triggering build for {node.package} on branch {self.args.branch}..."
                    )
                    pipeline = node.project.pipelines.trigger_build(self.args.branch)
                    if pipeline:
                        self.output.success(
                            f"  Successfully triggered build for {node.package}",
                        )
                        self.output.print(f"    Pipeline: {pipeline.web_url}")
                        total_builds += 1
                    else:
                        self.output.error(
                            f"  Failed to trigger build for {node.package}",
                        )
                        dag.mark_failed(node.package)
                        failed_builds += 1

            building_nodes = dag.get_nodes_by_status(DAGNodeStatus.BUILDING)
            if not building_nodes and not ready_nodes:
                break

            if building_nodes:
                self._poll_until_change(building_nodes, dag)

        blocked_nodes = dag.get_blocked_nodes()

        self.output.accent("\nBuild scheduling completed:")
        self.output.success(f"  Successfully triggered: {total_builds}")
        if failed_builds:
            self.output.error(f"  Failed: {failed_builds}")
        if blocked_nodes:
            blocked_names = sorted(n.package for n in blocked_nodes)
            self.output.warning(
                f"  Skipped (dependency failed): {', '.join(blocked_names)}",
            )

        if self.notify_service:
            self._send_build_notification(dag)

        self.storage_service.save_workspace_state(self.args.branch, dag)

        return 0

    def _poll_until_change(
        self, building_nodes: list[DAGNode], dag: DependencyGraph
    ) -> None:
        """Poll pipeline statuses until at least one building node completes or fails."""
        package_names = [node.package for node in building_nodes]
        if len(package_names) <= 3:
            packages_text = ", ".join(package_names)
        else:
            packages_text = ", ".join(package_names[:3]) + f"... ({len(package_names)} total)"

        self.output.accent(
            f"\nMonitoring builds: {packages_text}",
        )

        while True:
            changed = False
            for node in building_nodes:
                if node.status != DAGNodeStatus.BUILDING:
                    continue

                pkg = node.project
                if not pkg:
                    continue

                pipeline = pkg.pipelines.get_latest(self.args.branch, use_cache=False)
                if not pipeline:
                    continue

                if pipeline.status.is_successful:
                    self.output.success(f"  {node.package} completed successfully")
                    self.output.print(f"    Pipeline: {pipeline.web_url}")
                    dag.mark_succeeded(node.package)
                    changed = True
                elif pipeline.status.is_failed:
                    self.output.error(
                        f"  {node.package} failed: {pipeline.status.to_display_string()}",
                    )
                    self.output.print(f"    Pipeline: {pipeline.web_url}")
                    dag.mark_failed(node.package)
                    changed = True

            if changed:
                still_building = [
                    n for n in building_nodes if n.status == DAGNodeStatus.BUILDING
                ]
                if still_building:
                    names = [n.package for n in still_building]
                    if len(names) <= 3:
                        names_text = ", ".join(names)
                    else:
                        names_text = ", ".join(names[:3]) + f"... ({len(names)} total)"
                    self.output.muted(
                        f"Still waiting for {len(still_building)} packages: {names_text}",
                    )
                return

            time.sleep(self.args.poll_interval)

    def _generate_failing_package_commit_urls(self, failed_nodes: list[DAGNode]) -> dict[str, str]:
        """
        Generate commit URLs for failing packages when no previous DAG is available.

        Args:
            failed_nodes: List of failed DAG nodes

        Returns:
            Dict mapping package names to their commit URLs
        """
        return {
            node.package: node.project.commit_url(node.commit_sha)
            for node in failed_nodes
            if node.project and node.commit_sha
        }

    def _send_build_notification(self, dag: DependencyGraph) -> None:
        """Send notification about build results and generate comparison URLs for failed packages."""
        pipeline_urls = {}

        for package_name, node in dag.nodes.items():
            if node.project:
                pipeline = node.project.pipelines.get_latest(self.args.branch, use_cache=False)
                pipeline_urls[package_name] = pipeline.web_url if pipeline else "N/A"

        failed_nodes = dag.get_nodes_by_status(DAGNodeStatus.FAILED)
        successful_nodes = dag.get_nodes_by_status(DAGNodeStatus.SUCCESS)

        package_comparison_urls = {}

        # Only generate comparison URLs if there are failed packages
        if failed_nodes:
            if self.previous_dag:

                changed_packages = self.dependency_service.get_dag_changed_packages(self.previous_dag, dag)

                if changed_packages:
                    self.output.muted(
                        f"Generating comparison URLs for {len(changed_packages)} changed packages...",
                    )
                    package_comparison_urls = {
                        pkg: (
                            project.compare_url(old, new)
                            if old and new and old != new
                            else project.commit_url(new)
                        )
                        for pkg, (project, old, new) in changed_packages.items()
                        if project and new
                    }
                    self.output.muted(
                        f"Generated {len(package_comparison_urls)} comparison URLs",
                    )
            else:
                self.output.muted(
                    f"Generating commit URLs for {len(failed_nodes)} failing packages...",
                )
                package_comparison_urls = self._generate_failing_package_commit_urls(failed_nodes)
                self.output.muted(f"Generated {len(package_comparison_urls)} commit URLs")

        self.output.warning("\nSending build status notification...")
        failed_packages = [node.package for node in failed_nodes]
        successful_packages = [node.package for node in successful_nodes]
        notification_data = NotificationData(
            failed_packages=failed_packages,
            successful_packages=successful_packages,
            dag_nodes=dag.nodes,
            pipeline_urls=pipeline_urls,
            package_comparison_urls=package_comparison_urls,
        )

        success = self.notify_service.send_workspace_notification(self.args.branch, notification_data)
        if success:
            self.output.success("Build status notification sent successfully")
            if package_comparison_urls:
                if self.previous_dag:
                    self.output.success(
                        f"Included {len(package_comparison_urls)} package comparison URLs",
                    )
                else:
                    self.output.success(
                        f"Included {len(package_comparison_urls)} failing package commit URLs",
                    )
        else:
            self.output.error("Failed to send build status notification")
