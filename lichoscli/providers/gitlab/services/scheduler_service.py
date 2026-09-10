# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of SchedulerService."""

import logging
import time
from typing import TYPE_CHECKING, Optional

from lichoscli.core.models.build_schedule_result import BuildScheduleResult
from lichoscli.core.models.dag import DAGNodeStatus, DependencyGraph
from lichoscli.core.models.pipeline_status import PipelineStatus
from lichoscli.core.models.reverse_dependency_report import (
    ReverseDependencyEntry,
    ReverseDependencyReport,
)
from lichoscli.core.models.schedule_analysis import ScheduleAnalysis
from lichoscli.core.services.commit_status import CommitNodeStatus, WorkspaceStatus
from lichoscli.core.services.dependency import DependencyService
from lichoscli.core.services.notify import NotificationData, NotifyService
from lichoscli.core.services.scheduler_listener import SchedulerListener
from lichoscli.core.services.scheduler_service import SchedulerService
from lichoscli.core.services.storage import StorageService

if TYPE_CHECKING:
    from lichoscli.core.models.dag import DAGNode
    from lichoscli.core.models.pipeline import Pipeline
    from lichoscli.core.models.project import Project
    from lichoscli.core.models.workspace import Workspace
    from lichoscli.core.services.commit_status import CommitStatusService

logger = logging.getLogger(__name__)


class GitLabSchedulerService(SchedulerService):
    """GitLab-backed scheduler service using the core DAG scheduling primitives."""

    def __init__(
        self,
        dependency_service: DependencyService,
        storage_service: StorageService,
        commit_status_service: "CommitStatusService",
        notify_service: Optional[NotifyService],
    ):
        self._dependency_service = dependency_service
        self._storage_service = storage_service
        self._commit_status_service = commit_status_service
        self._notify_service = notify_service


    def prepare_schedule(
        self,
        packages: list["Project"],
        branch: str,
        skip_version_check: bool = False,
        previous_dag: Optional[DependencyGraph] = None,
    ) -> ScheduleAnalysis:
        dag = self._dependency_service.build_dependency_dag(packages, branch)
        if not dag:
            return ScheduleAnalysis(
                dag=DependencyGraph(nodes={}),
                skipped=True,
                skip_reason="Could not build dependency DAG",
            )

        if previous_dag and not skip_version_check:
            if not self._dependency_service.has_dag_state_changed(previous_dag, dag):
                return ScheduleAnalysis(
                    dag=dag,
                    skipped=True,
                    skip_reason="No changes to build graph state since last run",
                )

        if skip_version_check:
            for node in dag.nodes.values():
                node.set_status(DAGNodeStatus.PENDING)
            return ScheduleAnalysis(
                dag=dag,
                packages_needing_rebuild=set(dag.nodes.keys()),
            )

        return self._analyse_versions(dag)

    def _analyse_versions(self, dag: DependencyGraph) -> ScheduleAnalysis:
        """Run version checks and determine rebuild set."""
        packages_needing_rebuild: set[str] = set()

        for package_name, node in dag.nodes.items():
            if node.status == DAGNodeStatus.FAILED:
                packages_needing_rebuild.add(package_name)

        version_check_results = (
            self._dependency_service.check_all_dependency_versions_from_dag(dag)
        )

        for result in version_check_results:
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

        dag.apply_version_check_results(version_check_results)

        initial_rebuild_packages = packages_needing_rebuild.copy()
        for package_name in initial_rebuild_packages:
            transitive_dependents = dag.get_transitive_dependents(package_name)
            packages_needing_rebuild.update(node.package for node in transitive_dependents)

        for package_name, node in dag.nodes.items():
            if package_name in packages_needing_rebuild:
                node.set_status(DAGNodeStatus.PENDING)
                node.is_stale = package_name in initial_rebuild_packages
            else:
                node.set_status(DAGNodeStatus.SUCCESS)
                node.is_stale = False

        return ScheduleAnalysis(
            dag=dag,
            packages_needing_rebuild=packages_needing_rebuild,
            version_check_results=version_check_results,
        )


    def analyze_reverse_dependencies(
        self,
        workspace_packages: list["Project"],
        all_packages: list["Project"],
        branch: str,
    ) -> ReverseDependencyReport:
        workspace_names = {pkg.name for pkg in workspace_packages}

        dag = self._dependency_service.build_dependency_dag(
            all_packages, branch, wait_for_completion=False
        )
        if not dag or not dag.nodes:
            return ReverseDependencyReport()

        dependents: dict[str, "DAGNode"] = {}
        for pkg in workspace_packages:
            for node in dag.get_transitive_dependents(pkg.name):
                dependents[node.package] = node

        depth_memo: dict[str, int] = {}
        entries = [
            ReverseDependencyEntry(
                name=node.package,
                version=node.version,
                depth=dag.get_depth(node.package, depth_memo),
                in_workspace=node.package in workspace_names,
            )
            for node in dependents.values()
        ]
        entries.sort(key=lambda entry: (entry.in_workspace, entry.depth, entry.name))

        return ReverseDependencyReport(entries=entries)


    def execute_schedule(
        self,
        dag: DependencyGraph,
        workspace: "Workspace",
        poll_interval: int,
        listener: SchedulerListener,
    ) -> BuildScheduleResult:
        branch = workspace.name
        total_builds = 0
        failed_builds = 0

        while True:
            ready_nodes = dag.get_ready_nodes()

            if ready_nodes:
                for node in ready_nodes:
                    dag.mark_building(node.package)
                    pipeline = node.project.pipelines.trigger_build(branch)
                    if pipeline:
                        node.commit_sha = pipeline.sha
                        node.pipeline_url = pipeline.web_url
                        listener.on_build_triggered(node.package, pipeline.web_url)
                        total_builds += 1
                    else:
                        listener.on_trigger_failed(node.package)
                        dag.mark_failed(node.package)
                        failed_builds += 1

                self.post_dag_statuses(dag, workspace)

            building_nodes = dag.get_nodes_by_status(DAGNodeStatus.BUILDING)
            if not building_nodes and not ready_nodes:
                break

            if building_nodes:
                self._poll_until_change(building_nodes, dag, workspace, poll_interval, listener)

        blocked_nodes = dag.get_blocked_nodes()

        blocked_names = sorted(n.package for n in blocked_nodes)
        if blocked_names:
            listener.on_blocked(blocked_names)

        return BuildScheduleResult(
            total_builds=total_builds,
            failed_builds=failed_builds,
            blocked_packages=blocked_names,
        )

    def _poll_until_change(
        self,
        building_nodes: list["DAGNode"],
        dag: DependencyGraph,
        workspace: "Workspace",
        poll_interval: int,
        listener: SchedulerListener,
    ) -> None:
        """Poll pipeline statuses until at least one building node completes or fails."""
        branch = workspace.name
        package_names = [node.package for node in building_nodes]
        listener.on_polling_start(package_names)

        while True:
            changed = False
            for node in building_nodes:
                if node.status != DAGNodeStatus.BUILDING:
                    continue

                pkg = node.project
                if not pkg:
                    continue

                pipeline = pkg.pipelines.get_latest(branch, use_cache=False)
                if not pipeline:
                    continue

                logger.debug(
                    "Pipeline %s for %s: status=%s",
                    pipeline.id,
                    node.package,
                    pipeline.status.to_display_string(),
                )

                failure_reason = self._detect_pipeline_outcome(pipeline)

                if pipeline.is_publish_complete():
                    logger.debug(
                        "Pipeline %s for %s transitioned to: success (publish complete)",
                        pipeline.id,
                        node.package,
                    )
                    node.pipeline_url = pipeline.web_url
                    dag.mark_succeeded(node.package)
                    listener.on_build_succeeded(node.package, pipeline.web_url)
                    changed = True
                elif failure_reason:
                    logger.debug(
                        "Pipeline %s for %s transitioned to: failed (%s)",
                        pipeline.id,
                        node.package,
                        failure_reason,
                    )
                    node.pipeline_url = pipeline.web_url
                    dag.mark_failed(node.package)
                    listener.on_build_failed(node.package, failure_reason)
                    changed = True

            if changed:
                self.post_dag_statuses(dag, workspace)
                still_building = [
                    n.package for n in building_nodes if n.status == DAGNodeStatus.BUILDING
                ]
                if still_building:
                    listener.on_polling_update(still_building)
                return

            time.sleep(poll_interval)

    @staticmethod
    def _detect_pipeline_outcome(pipeline: "Pipeline") -> Optional[str]:
        """Return a failure reason string if the pipeline should be treated as failed."""
        if pipeline.status.is_failed:
            return "failed: {0}".format(pipeline.status.to_display_string())
        if pipeline.has_failed_jobs():
            return "has failed jobs (pipeline still {0})".format(
                pipeline.status.to_display_string()
            )
        if pipeline.status.is_final:
            return "ended without publishing: {0}".format(
                pipeline.status.to_display_string()
            )
        return None

    def post_dag_statuses(
        self,
        dag: DependencyGraph,
        workspace: "Workspace",
        scheduling_complete: bool = False,
        missing_dependencies: Optional[list[str]] = None,
    ) -> None:
        if workspace.is_protected:
            logger.info(
                "Skipping workspace-scheduling status: workspace '%s' is a protected branch",
                workspace.name,
            )
            return

        extra_description = None
        if missing_dependencies:
            extra_description = "build deps not in workspace: {0}".format(
                ", ".join(sorted(missing_dependencies))
            )

        has_failures = any(
            node.status == DAGNodeStatus.FAILED for node in dag.nodes.values()
        )

        groups: dict[WorkspaceStatus, tuple[dict, dict]] = {
            WorkspaceStatus.FAILED: ({}, {}),
            WorkspaceStatus.STALE: ({}, {}),
            WorkspaceStatus.BUILDING: ({}, {}),
            WorkspaceStatus.SUCCESS: ({}, {}),
        }

        for name, node in dag.nodes.items():
            if not node.commit_sha or not node.project:
                logger.warning(
                    "Skipping commit status for %s: missing commit_sha or project",
                    node.package,
                )
                continue

            ws = self._resolve_node_workspace_status(
                node.status, scheduling_complete, has_failures,
            )

            projs, shas = groups[ws]
            projs[name] = node.project
            shas[name] = node.commit_sha

        for ws, (projs, shas) in groups.items():
            if projs:
                if extra_description:
                    self._commit_status_service.post_workspace_status(
                        projs, shas, ws, extra_description
                    )
                else:
                    self._commit_status_service.post_workspace_status(projs, shas, ws)

    @staticmethod
    def _resolve_node_workspace_status(
        node_status: DAGNodeStatus,
        scheduling_complete: bool,
        has_failures: bool,
    ) -> WorkspaceStatus:
        """Derive the workspace-scheduling commit status for one node.

        The status is workspace-global: it depends not only on the
        node's own DAG status but also on whether the scheduling run
        is still in progress and whether any node in the workspace has
        failed.
        """
        if scheduling_complete:
            if has_failures:
                if node_status == DAGNodeStatus.FAILED:
                    return WorkspaceStatus.FAILED
                return WorkspaceStatus.STALE
            return WorkspaceStatus.SUCCESS

        # Scheduling in progress
        if node_status == DAGNodeStatus.FAILED:
            return WorkspaceStatus.FAILED
        if node_status == DAGNodeStatus.PENDING:
            return WorkspaceStatus.STALE
        # BUILDING and SUCCESS both stay BUILDING while scheduling runs
        return WorkspaceStatus.BUILDING

    def send_build_notification(
        self,
        dag: DependencyGraph,
        workspace: "Workspace",
        previous_dag: Optional[DependencyGraph] = None,
    ) -> bool:
        if not self._notify_service:
            return False

        branch = workspace.name

        pipeline_urls: dict[str, str] = {
            name: node.pipeline_url or "N/A"
            for name, node in dag.nodes.items()
        }

        failed_nodes = dag.get_nodes_by_status(DAGNodeStatus.FAILED)
        successful_nodes = dag.get_nodes_by_status(DAGNodeStatus.SUCCESS)

        package_comparison_urls: dict[str, str] = {}

        if failed_nodes:
            if previous_dag:
                changed_packages = self._dependency_service.get_dag_changed_packages(
                    previous_dag, dag
                )
                if changed_packages:
                    package_comparison_urls = {
                        pkg: (
                            project.compare_url(old, new)
                            if old and new and old != new
                            else project.commit_url(new)
                        )
                        for pkg, (project, old, new) in changed_packages.items()
                        if project and new
                    }
            else:
                package_comparison_urls = {
                    node.package: node.project.commit_url(node.commit_sha)
                    for node in failed_nodes
                    if node.project and node.commit_sha
                }

        notification_data = NotificationData(
            failed_packages=[node.package for node in failed_nodes],
            successful_packages=[node.package for node in successful_nodes],
            dag_nodes=dag.nodes,
            pipeline_urls=pipeline_urls,
            package_comparison_urls=package_comparison_urls,
        )

        return self._notify_service.send_workspace_notification(branch, notification_data)


    def cancel_orphan_pipelines(
        self,
        packages: list["Project"],
        branch: str,
    ) -> list[str]:
        """Cancel pipelines kept running only by an orphaned workspace status."""
        cancelled: list[str] = []
        for pkg in packages:
            running_pipelines = pkg.pipelines.list(
                branch,
                status=PipelineStatus.RUNNING.value,
                get_all=True,
            )
            for pipeline in running_pipelines:
                if not self._commit_status_service.is_pipeline_orphaned(
                    pkg,
                    pipeline.sha,
                    pipeline.id,
                ):
                    continue
                logger.info(
                    "Cancelling orphan pipeline %s for %s (status: %s)",
                    pipeline.id,
                    pkg.name,
                    pipeline.status.value,
                )
                if not pipeline.cancel():
                    logger.warning(
                        "Failed to cancel orphan pipeline %s for %s",
                        pipeline.id,
                        pkg.name,
                    )
                    continue
                self._commit_status_service.post_node_status(
                    pkg,
                    pipeline.sha,
                    CommitNodeStatus.CANCELLED,
                    pipeline.id,
                    pipeline.web_url,
                )
                if pkg.name not in cancelled:
                    cancelled.append(pkg.name)
            if pkg.name in cancelled:
                pkg.pipelines.invalidate(branch)
        return cancelled

    def persist_state(self, workspace: "Workspace", dag: DependencyGraph) -> None:
        self._storage_service.save_workspace_state(workspace.name, dag)

    def await_running_pipelines(
        self,
        packages: list["Project"],
        branch: str,
        poll_interval: int,
        listener: SchedulerListener,
    ) -> None:
        """Wait for any running pipelines in the workspace to complete.

        Emits ``on_waiting_for_pipelines`` synchronously before polling so
        the user is told which pipelines are still running, even if the
        wait lasts minutes. The same ``listener`` passed to
        ``execute_schedule`` can be reused here.
        """
        running: dict[str, "Project"] = {}

        for pkg in packages:
            pipeline = pkg.pipelines.get_latest(branch, use_cache=False)
            if not pipeline:
                continue
            if not pipeline.is_publish_complete() and not self._detect_pipeline_outcome(pipeline):
                running[pkg.name] = pkg

        if not running:
            return

        listener.on_waiting_for_pipelines(sorted(running.keys()))

        while running:
            time.sleep(poll_interval)
            for name in list(running.keys()):
                pkg = running[name]
                pipeline = pkg.pipelines.get_latest(branch, use_cache=False)
                if not pipeline:
                    del running[name]
                    continue
                if pipeline.is_publish_complete() or self._detect_pipeline_outcome(pipeline):
                    logger.info("Pipeline for %s completed", name)
                    del running[name]
