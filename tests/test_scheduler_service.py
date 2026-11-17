# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

import pytest

from lichoscli.core.models.dag import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.core.models.build_schedule_result import BuildScheduleResult
from lichoscli.core.models.schedule_analysis import ScheduleAnalysis
from lichoscli.core.services.commit_status import CommitNodeStatus, CommitStatusService
from lichoscli.core.models.dag import WorkspaceStatus
from lichoscli.core.services.dependency import DependencyService, VersionCheckResult
from lichoscli.core.services.notify import NotifyService
from lichoscli.core.services.scheduler_listener import SchedulerListener
from lichoscli.core.services.storage import StorageService
from lichoscli.providers.gitlab.services.scheduler_service import GitLabSchedulerService


# ── helpers ──────────────────────────────────────────────────────────


def _node(name, status=DAGNodeStatus.PENDING, project=None, commit_sha=None):
    return DAGNode(
        package=name,
        version="1.0",
        architecture="amd64",
        status=status,
        project=project,
        commit_sha=commit_sha,
    )


def _diamond_dag(project_factory=None):
    """Build A → B, A → C, B → D, C → D with optional mock projects."""
    nodes = {}
    for name in ("A", "B", "C", "D"):
        proj = project_factory(name) if project_factory else None
        nodes[name] = _node(name, project=proj, commit_sha="sha-{0}".format(name.lower()))

    nodes["B"].add_dependency(nodes["A"])
    nodes["A"].add_dependent(nodes["B"])
    nodes["C"].add_dependency(nodes["A"])
    nodes["A"].add_dependent(nodes["C"])
    nodes["D"].add_dependency(nodes["B"])
    nodes["B"].add_dependent(nodes["D"])
    nodes["D"].add_dependency(nodes["C"])
    nodes["C"].add_dependent(nodes["D"])

    return DependencyGraph(nodes=nodes)


def _make_service(
    dependency_service=None,
    storage_service=None,
    commit_status_service=None,
    notify_service=None,
):
    return GitLabSchedulerService(
        dependency_service=dependency_service or Mock(spec=DependencyService),
        storage_service=storage_service or Mock(spec=StorageService),
        commit_status_service=commit_status_service or Mock(spec=CommitStatusService),
        notify_service=notify_service,
    )


# ── prepare_schedule ─────────────────────────────────────────────────


class TestPrepareSchedule:
    def test_skip_version_check_marks_all_pending(self):
        dep_svc = Mock(spec=DependencyService)
        dag = _diamond_dag()
        dep_svc.build_dependency_dag.return_value = dag

        svc = _make_service(dependency_service=dep_svc)
        result = svc.prepare_schedule(
            packages=[],
            branch="main",
            skip_version_check=True,
        )

        assert not result.skipped
        assert result.packages_needing_rebuild == {"A", "B", "C", "D"}
        for node in result.dag.nodes.values():
            assert node.status == DAGNodeStatus.PENDING

    def test_no_dag_returns_skipped(self):
        dep_svc = Mock(spec=DependencyService)
        dep_svc.build_dependency_dag.return_value = None

        svc = _make_service(dependency_service=dep_svc)
        result = svc.prepare_schedule(packages=[], branch="main")

        assert result.skipped is True

    def test_no_changes_since_last_run_returns_skipped(self):
        dep_svc = Mock(spec=DependencyService)
        dag = _diamond_dag()
        dep_svc.build_dependency_dag.return_value = dag
        dep_svc.has_dag_state_changed.return_value = False

        previous_dag = _diamond_dag()
        svc = _make_service(dependency_service=dep_svc)
        result = svc.prepare_schedule(
            packages=[],
            branch="main",
            previous_dag=previous_dag,
        )

        assert result.skipped is True
        assert "no changes" in result.skip_reason.lower()

    def test_version_mismatch_marks_dependent_and_transitive(self):
        dep_svc = Mock(spec=DependencyService)
        dag = _diamond_dag()
        dep_svc.build_dependency_dag.return_value = dag
        dep_svc.check_all_dependency_versions_from_dag.return_value = [
            VersionCheckResult(
                dependent_package="B",
                dependent_version="1.0",
                used_version="0.9",
                expected_version="1.0",
                is_correct=False,
                binary_package="liba",
                source_package="A",
            ),
        ]

        svc = _make_service(dependency_service=dep_svc)
        result = svc.prepare_schedule(packages=[], branch="main")

        assert "B" in result.packages_needing_rebuild
        assert "D" in result.packages_needing_rebuild  # transitive dependent of B
        assert result.dag.nodes["B"].status == DAGNodeStatus.PENDING
        assert result.dag.nodes["D"].status == DAGNodeStatus.PENDING
        assert result.dag.nodes["A"].status == DAGNodeStatus.SUCCESS
        assert result.dag.nodes["C"].status == DAGNodeStatus.SUCCESS

    def test_all_versions_correct_marks_all_success(self):
        dep_svc = Mock(spec=DependencyService)
        dag = _diamond_dag()
        # Ensure no nodes start as FAILED
        for node in dag.nodes.values():
            node.status = DAGNodeStatus.PENDING
        dep_svc.build_dependency_dag.return_value = dag
        dep_svc.check_all_dependency_versions_from_dag.return_value = [
            VersionCheckResult(
                dependent_package="B",
                dependent_version="1.0",
                used_version="1.0",
                expected_version="1.0",
                is_correct=True,
                binary_package="liba",
                source_package="A",
            ),
        ]

        svc = _make_service(dependency_service=dep_svc)
        result = svc.prepare_schedule(packages=[], branch="main")

        assert result.packages_needing_rebuild == set()
        for node in result.dag.nodes.values():
            assert node.status == DAGNodeStatus.SUCCESS


# ── execute_schedule ─────────────────────────────────────────────────


def _workspace(name="main", protected=False):
    ws = Mock()
    ws.name = name
    ws.is_protected = protected
    return ws


class TestExecuteSchedule:
    def _make_project(self, name):
        proj = Mock()
        proj.pipelines = Mock()
        return proj

    def test_successful_build_flow(self):
        proj_a = self._make_project("A")
        pipeline = Mock()
        pipeline.sha = "abc123"
        pipeline.web_url = "https://example.com/pipeline/1"
        pipeline.status = Mock()
        pipeline.status.is_failed = False
        pipeline.status.is_final = False
        pipeline.status.to_display_string.return_value = "success"
        pipeline.has_failed_jobs.return_value = False
        pipeline.is_publish_complete.return_value = True

        proj_a.pipelines.trigger_build.return_value = pipeline
        proj_a.pipelines.get_latest.return_value = pipeline

        node_a = _node("A", project=proj_a, commit_sha="old-sha")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            result = svc.execute_schedule(
                dag=dag, workspace=_workspace(), poll_interval=0, listener=Mock(spec=SchedulerListener)
            )

        assert result.total_builds == 1
        assert result.failed_builds == 0
        assert result.blocked_packages == []
        assert dag.nodes["A"].status == DAGNodeStatus.SUCCESS

    def test_trigger_failure(self):
        proj_a = self._make_project("A")
        proj_a.pipelines.trigger_build.return_value = None

        node_a = _node("A", project=proj_a, commit_sha="sha-a")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        result = svc.execute_schedule(dag=dag, workspace=_workspace(), poll_interval=0, listener=Mock(spec=SchedulerListener))

        assert result.total_builds == 0
        assert result.failed_builds == 1
        assert dag.nodes["A"].status == DAGNodeStatus.FAILED

    def test_trigger_failure_posts_workspace_status(self):
        proj_a = self._make_project("A")
        proj_a.pipelines.trigger_build.return_value = None
        proj_a.pipelines.get_latest.return_value = Mock(sha="sha-a")

        node_a = _node("A", project=proj_a, commit_sha="sha-a")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.execute_schedule(dag=dag, workspace=_workspace(), poll_interval=0, listener=Mock(spec=SchedulerListener))

        commit_svc.post_workspace_status.assert_called()
        last_call_status = commit_svc.post_workspace_status.call_args[0][1]
        assert last_call_status == WorkspaceStatus.FAILED

    def test_node_success_posts_building_during_scheduling(self):
        proj_a = self._make_project("A")
        pipeline = Mock()
        pipeline.sha = "abc123"
        pipeline.web_url = "https://example.com/pipeline/1"
        pipeline.status = Mock()
        pipeline.status.is_failed = False
        pipeline.status.is_final = False
        pipeline.status.to_display_string.return_value = "success"
        pipeline.has_failed_jobs.return_value = False
        pipeline.is_publish_complete.return_value = True
        proj_a.pipelines.trigger_build.return_value = pipeline
        proj_a.pipelines.get_latest.return_value = pipeline

        node_a = _node("A", project=proj_a, commit_sha="old-sha")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.execute_schedule(
                dag=dag, workspace=_workspace(), poll_interval=0, listener=Mock(spec=SchedulerListener)
            )

        # During execute_schedule, scheduling is in-progress so SUCCESS
        # nodes get BUILDING to block merges workspace-wide
        commit_svc.post_workspace_status.assert_called()
        last_call_status = commit_svc.post_workspace_status.call_args[0][1]
        assert last_call_status == WorkspaceStatus.BUILDING

    def test_blocked_nodes_reported(self):
        proj_a = self._make_project("A")
        proj_a.pipelines.trigger_build.return_value = None

        a = _node("A", project=proj_a, commit_sha="sha-a")
        b = _node("B", commit_sha="sha-b")
        b.add_dependency(a)
        a.add_dependent(b)
        dag = DependencyGraph(nodes={"A": a, "B": b})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        result = svc.execute_schedule(dag=dag, workspace=_workspace(), poll_interval=0, listener=Mock(spec=SchedulerListener))

        assert result.blocked_packages == ["B"]

    def test_trigger_updates_commit_sha_on_node(self):
        proj_a = self._make_project("A")
        pipeline = Mock()
        pipeline.sha = "new-sha-from-pipeline"
        pipeline.web_url = "https://example.com/pipeline/1"
        pipeline.status = Mock()
        pipeline.status.is_failed = False
        pipeline.status.is_final = False
        pipeline.status.to_display_string.return_value = "success"
        pipeline.has_failed_jobs.return_value = False
        pipeline.is_publish_complete.return_value = True
        proj_a.pipelines.trigger_build.return_value = pipeline
        proj_a.pipelines.get_latest.return_value = pipeline

        node_a = _node("A", project=proj_a, commit_sha="old-sha-from-dag")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.execute_schedule(
                dag=dag, workspace=_workspace(), poll_interval=0, listener=Mock(spec=SchedulerListener)
            )
        # post_dag_statuses should have been called with the new SHA
        posted_nodes = commit_svc.post_workspace_status.call_args[0][0]
        assert posted_nodes[0].commit_sha == "new-sha-from-pipeline"


# ── post_dag_statuses ────────────────────────────────────────────────


class TestPostDagStatuses:
    def test_all_success_scheduling_complete_posts_success(self):
        proj_a = Mock()
        proj_b = Mock()

        node_a = _node("A", status=DAGNodeStatus.SUCCESS, project=proj_a, commit_sha="sha-a")
        node_b = _node("B", status=DAGNodeStatus.SUCCESS, project=proj_b, commit_sha="sha-b")
        dag = DependencyGraph(nodes={"A": node_a, "B": node_b})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace(), scheduling_complete=True)

        commit_svc.post_workspace_status.assert_called_once_with(
            [node_a, node_b], WorkspaceStatus.SUCCESS, "main", None
        )

    def test_success_nodes_get_building_during_scheduling(self):
        proj_a = Mock()
        proj_b = Mock()

        node_a = _node("A", status=DAGNodeStatus.SUCCESS, project=proj_a, commit_sha="sha-a")
        node_b = _node("B", status=DAGNodeStatus.SUCCESS, project=proj_b, commit_sha="sha-b")
        dag = DependencyGraph(nodes={"A": node_a, "B": node_b})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        commit_svc.post_workspace_status.assert_called_once_with(
            [node_a, node_b], WorkspaceStatus.BUILDING, "main", None
        )

    def test_failure_marks_others_stale_when_complete(self):
        proj_a = Mock()
        proj_b = Mock()

        node_a = _node("A", status=DAGNodeStatus.FAILED, project=proj_a, commit_sha="sha-a")
        node_b = _node("B", status=DAGNodeStatus.SUCCESS, project=proj_b, commit_sha="sha-b")
        dag = DependencyGraph(nodes={"A": node_a, "B": node_b})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace(), scheduling_complete=True)

        calls = {call[0][1]: call[0] for call in commit_svc.post_workspace_status.call_args_list}
        assert WorkspaceStatus.FAILED in calls
        assert WorkspaceStatus.STALE in calls
        assert calls[WorkspaceStatus.FAILED][0] == [node_a]
        assert calls[WorkspaceStatus.STALE][0] == [node_b]

    def test_failed_node_posts_workspace_failed(self):
        proj = Mock()
        node = _node("A", status=DAGNodeStatus.FAILED, project=proj, commit_sha="sha")
        dag = DependencyGraph(nodes={"A": node})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        commit_svc.post_workspace_status.assert_called_once_with(
            [node], WorkspaceStatus.FAILED, "main", None
        )

    def test_building_node_posts_workspace_building(self):
        proj = Mock()
        node = _node("A", status=DAGNodeStatus.BUILDING, project=proj, commit_sha="sha")
        dag = DependencyGraph(nodes={"A": node})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        commit_svc.post_workspace_status.assert_called_once_with(
            [node], WorkspaceStatus.BUILDING, "main", None
        )

    def test_missing_commit_sha_skipped(self):
        proj = Mock()
        node = _node("A", status=DAGNodeStatus.SUCCESS, project=proj)
        dag = DependencyGraph(nodes={"A": node})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        commit_svc.post_workspace_status.assert_not_called()

    def test_blocked_node_gets_stale_not_failed(self):
        proj_a = Mock()
        proj_b = Mock()

        node_a = _node("A", status=DAGNodeStatus.FAILED, project=proj_a, commit_sha="sha-a")
        node_b = _node("B", status=DAGNodeStatus.PENDING, project=proj_b, commit_sha="sha-b")
        node_b.add_dependency(node_a)
        node_a.add_dependent(node_b)
        dag = DependencyGraph(nodes={"A": node_a, "B": node_b})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        calls = {call[0][1]: call[0] for call in commit_svc.post_workspace_status.call_args_list}
        assert WorkspaceStatus.FAILED in calls
        assert WorkspaceStatus.STALE in calls
        assert calls[WorkspaceStatus.FAILED][0] == [node_a]
        assert calls[WorkspaceStatus.STALE][0] == [node_b]

    def test_pending_node_gets_stale_not_building(self):
        proj = Mock()
        node = _node("A", status=DAGNodeStatus.PENDING, project=proj, commit_sha="sha")
        dag = DependencyGraph(nodes={"A": node})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        commit_svc.post_workspace_status.assert_called_once_with(
            [node], WorkspaceStatus.STALE, "main", None
        )

    def test_mixed_states_during_scheduling(self):
        proj_a = Mock()
        proj_b = Mock()
        proj_c = Mock()

        node_a = _node("A", status=DAGNodeStatus.BUILDING, project=proj_a, commit_sha="sha-a")
        node_b = _node("B", status=DAGNodeStatus.PENDING, project=proj_b, commit_sha="sha-b")
        node_c = _node("C", status=DAGNodeStatus.SUCCESS, project=proj_c, commit_sha="sha-c")
        dag = DependencyGraph(nodes={"A": node_a, "B": node_b, "C": node_c})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        calls = {call[0][1]: call[0] for call in commit_svc.post_workspace_status.call_args_list}
        # BUILDING and SUCCESS both get BUILDING during scheduling
        assert WorkspaceStatus.BUILDING in calls
        assert calls[WorkspaceStatus.BUILDING][0] == [node_a, node_c]
        # PENDING gets STALE
        assert WorkspaceStatus.STALE in calls
        assert calls[WorkspaceStatus.STALE][0] == [node_b]

    def test_protected_workspace_skips_all_posting(self):
        proj = Mock()
        node = _node("A", status=DAGNodeStatus.SUCCESS, project=proj, commit_sha="sha")
        dag = DependencyGraph(nodes={"A": node})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace(protected=True))

        commit_svc.post_workspace_status.assert_not_called()

    def test_unprotected_workspace_posts_normally(self):
        proj = Mock()
        node = _node("A", status=DAGNodeStatus.SUCCESS, project=proj, commit_sha="sha")
        dag = DependencyGraph(nodes={"A": node})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)
        svc.post_dag_statuses(dag, _workspace())

        commit_svc.post_workspace_status.assert_called_once()


# ── persist_state ────────────────────────────────────────────────────


class TestPersistState:
    def test_delegates_to_storage_service(self):
        storage_svc = Mock(spec=StorageService)
        dag = DependencyGraph(nodes={})
        svc = _make_service(storage_service=storage_svc)
        svc.persist_state(_workspace("main"), dag)
        storage_svc.save_workspace_state.assert_called_once_with("main", dag)


# ── send_build_notification ──────────────────────────────────────────


class TestSendBuildNotification:
    def test_no_notify_service_returns_false(self):
        svc = _make_service(notify_service=None)
        dag = DependencyGraph(nodes={})
        assert svc.send_build_notification(dag, _workspace("main")) is False

    def test_sends_notification_with_failed_packages(self):
        notify_svc = Mock(spec=NotifyService)
        notify_svc.send_workspace_notification.return_value = True

        proj = Mock()
        proj.pipelines.get_latest.return_value = Mock(web_url="https://example.com/p/1")
        proj.commit_url.return_value = "https://example.com/commit/sha"

        node = _node("A", status=DAGNodeStatus.FAILED, project=proj, commit_sha="sha")
        dag = DependencyGraph(nodes={"A": node})

        svc = _make_service(notify_service=notify_svc)
        result = svc.send_build_notification(dag, _workspace("main"))

        assert result is True
        notify_svc.send_workspace_notification.assert_called_once()
        call_args = notify_svc.send_workspace_notification.call_args
        notification_data = call_args[0][1]
        assert "A" in notification_data.failed_packages


class TestCancelOrphanPipelines:
    @staticmethod
    def _project_with_pipeline(pipeline):
        project = Mock()
        project.name = "package-a"
        project.pipelines.list.return_value = [pipeline]
        return project

    @staticmethod
    def _pipeline():
        pipeline = Mock()
        pipeline.id = 123
        pipeline.sha = "sha-a"
        pipeline.web_url = "https://example.com/pipelines/123"
        pipeline.status.value = "running"
        return pipeline

    def test_non_orphaned_pipeline_remains_active(self):
        """Scheduler cleanup must preserve a pipeline not classified as orphaned."""
        pipeline = self._pipeline()
        project = self._project_with_pipeline(pipeline)
        commit_status_service = Mock(spec=CommitStatusService)
        commit_status_service.is_pipeline_orphaned.return_value = False
        service = _make_service(commit_status_service=commit_status_service)

        cancelled = service.cancel_orphan_pipelines([project], "flocken")

        expectation = "Expected a non-orphaned pipeline to remain active"
        assert not cancelled, expectation
        project.pipelines.list.assert_called_once_with(
            "flocken", status="running", get_all=True
        )
        pipeline.cancel.assert_not_called()
        commit_status_service.post_node_status.assert_not_called()

    def test_orphaned_pipeline_is_cancelled(self):
        """Scheduler cleanup must cancel a pipeline classified as orphaned."""
        pipeline = self._pipeline()
        pipeline.cancel.return_value = True
        project = self._project_with_pipeline(pipeline)
        commit_status_service = Mock(spec=CommitStatusService)
        commit_status_service.is_pipeline_orphaned.return_value = True
        service = _make_service(commit_status_service=commit_status_service)

        cancelled = service.cancel_orphan_pipelines([project], "feature/flocken")

        expectation = "Expected the orphaned package to be reported"
        assert cancelled == ["package-a"], expectation
        pipeline.cancel.assert_called_once_with()
        commit_status_service.post_node_status.assert_called_once_with(
            project,
            "sha-a",
            CommitNodeStatus.CANCELLED,
            123,
            "https://example.com/pipelines/123",
        )

    def test_failed_orphan_cancellation_is_not_reported_as_success(self):
        """Scheduler cleanup must report cancellation only after GitLab accepts it."""
        pipeline = self._pipeline()
        pipeline.cancel.return_value = False
        project = self._project_with_pipeline(pipeline)
        commit_status_service = Mock(spec=CommitStatusService)
        commit_status_service.is_pipeline_orphaned.return_value = True
        service = _make_service(commit_status_service=commit_status_service)

        cancelled = service.cancel_orphan_pipelines([project], "feature/flocken")

        assert not cancelled
        pipeline.cancel.assert_called_once_with()
        commit_status_service.post_node_status.assert_not_called()
        project.pipelines.invalidate.assert_not_called()


# ── await_running_pipelines ──────────────────────────────────────────


class TestAwaitRunningPipelines:
    def _make_project(self, name):
        proj = Mock()
        proj.name = name
        proj.pipelines = Mock()
        return proj

    def _finished_pipeline(self):
        pipeline = Mock()
        pipeline.is_publish_complete.return_value = True
        pipeline.has_failed_jobs.return_value = False
        pipeline.status = Mock()
        pipeline.status.is_failed = False
        pipeline.status.is_final = False
        return pipeline

    def _running_pipeline(self):
        pipeline = Mock()
        pipeline.is_publish_complete.return_value = False
        pipeline.has_failed_jobs.return_value = False
        pipeline.status = Mock()
        pipeline.status.is_failed = False
        pipeline.status.is_final = False
        pipeline.status.to_display_string.return_value = "running"
        return pipeline

    def test_returns_immediately_when_no_running_pipelines(self):
        proj_a = self._make_project("A")
        proj_a.pipelines.get_latest.return_value = self._finished_pipeline()

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        svc.await_running_pipelines(
            [proj_a], "main", poll_interval=0, listener=listener,
        )

        listener.on_waiting_for_pipelines.assert_not_called()
        # Only the initial check call, no polling
        proj_a.pipelines.get_latest.assert_called_once_with("main", use_cache=False)

    def test_returns_immediately_when_no_pipelines(self):
        proj_a = self._make_project("A")
        proj_a.pipelines.get_latest.return_value = None

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        svc.await_running_pipelines(
            [proj_a], "main", poll_interval=0, listener=listener,
        )

        listener.on_waiting_for_pipelines.assert_not_called()
        proj_a.pipelines.get_latest.assert_called_once()

    def test_waits_for_running_pipeline_to_finish(self):
        proj_a = self._make_project("A")
        running = self._running_pipeline()
        finished = self._finished_pipeline()
        proj_a.pipelines.get_latest.side_effect = [running, finished]

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.await_running_pipelines(
                [proj_a], "main", poll_interval=0, listener=listener,
            )

        listener.on_waiting_for_pipelines.assert_called_once_with(["A"])
        assert proj_a.pipelines.get_latest.call_count == 2

    def test_waits_for_failed_pipeline_detection(self):
        proj_a = self._make_project("A")
        running = self._running_pipeline()
        failed = Mock()
        failed.is_publish_complete.return_value = False
        failed.has_failed_jobs.return_value = False
        failed.status = Mock()
        failed.status.is_failed = True
        failed.status.is_final = True
        failed.status.to_display_string.return_value = "failed"
        proj_a.pipelines.get_latest.side_effect = [running, failed]

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.await_running_pipelines(
                [proj_a], "main", poll_interval=0, listener=listener,
            )

        listener.on_waiting_for_pipelines.assert_called_once_with(["A"])
        assert proj_a.pipelines.get_latest.call_count == 2

    def test_handles_pipeline_disappearing_during_poll(self):
        proj_a = self._make_project("A")
        running = self._running_pipeline()
        proj_a.pipelines.get_latest.side_effect = [running, None]

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.await_running_pipelines(
                [proj_a], "main", poll_interval=0, listener=listener,
            )

        listener.on_waiting_for_pipelines.assert_called_once_with(["A"])
        assert proj_a.pipelines.get_latest.call_count == 2

    def test_multiple_packages_waits_for_all(self):
        proj_a = self._make_project("A")
        proj_b = self._make_project("B")

        running = self._running_pipeline()
        finished = self._finished_pipeline()

        proj_a.pipelines.get_latest.side_effect = [running, finished]
        proj_b.pipelines.get_latest.return_value = finished

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.await_running_pipelines(
                [proj_a, proj_b], "main", poll_interval=0, listener=listener,
            )

        # Only A is still running at detection time
        listener.on_waiting_for_pipelines.assert_called_once_with(["A"])
        # proj_b: 1 initial call (already finished, not polled)
        proj_b.pipelines.get_latest.assert_called_once()
        # proj_a: 1 initial + 1 poll call
        assert proj_a.pipelines.get_latest.call_count == 2

    def test_listener_called_with_all_running_packages_sorted(self):
        proj_a = self._make_project("zeta")
        proj_b = self._make_project("alpha")
        proj_c = self._make_project("mu")

        running = self._running_pipeline()
        finished = self._finished_pipeline()
        proj_a.pipelines.get_latest.side_effect = [running, finished]
        proj_b.pipelines.get_latest.side_effect = [running, finished]
        proj_c.pipelines.get_latest.side_effect = [running, finished]

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        with patch("lichoscli.providers.gitlab.services.scheduler_service.time.sleep"):
            svc.await_running_pipelines(
                [proj_a, proj_b, proj_c], "main", poll_interval=0, listener=listener,
            )

        listener.on_waiting_for_pipelines.assert_called_once_with(
            ["alpha", "mu", "zeta"]
        )

    def test_listener_notified_before_polling_starts(self):
        """Regression: the 'Waiting' message must reach the user
        immediately, not after the wait completes.

        Verifies that listener.on_waiting_for_pipelines fires before the
        first time.sleep() poll tick. If the message fired after the
        wait, events would record "sleep" first.
        """
        proj_a = self._make_project("A")
        running = self._running_pipeline()
        finished = self._finished_pipeline()
        proj_a.pipelines.get_latest.side_effect = [running, finished]

        svc = _make_service()
        listener = Mock(spec=SchedulerListener)
        events: list[str] = []
        listener.on_waiting_for_pipelines.side_effect = (
            lambda pkgs: events.append("listener")
        )
        with patch(
            "lichoscli.providers.gitlab.services.scheduler_service.time.sleep",
            side_effect=lambda _secs: events.append("sleep") or None,
        ):
            svc.await_running_pipelines(
                [proj_a], "main", poll_interval=0, listener=listener,
            )

        listener.on_waiting_for_pipelines.assert_called_once_with(["A"])
        assert events, "expected sleep to run"
        assert events[0] == "listener"
        assert events.count("listener") == 1


class TestAnalyzeReverseDependencies:
    @staticmethod
    def _pkg(name):
        pkg = Mock()
        pkg.name = name
        return pkg

    @staticmethod
    def _chain_dag():
        """Build A → B → C (C depends on B, B depends on A)."""
        nodes = {name: _node(name) for name in ("A", "B", "C")}
        nodes["B"].add_dependency(nodes["A"])
        nodes["A"].add_dependent(nodes["B"])
        nodes["C"].add_dependency(nodes["B"])
        nodes["B"].add_dependent(nodes["C"])
        return DependencyGraph(nodes=nodes)

    def test_classifies_in_workspace_and_missing(self):
        dependency_service = Mock(spec=DependencyService)
        dependency_service.build_dependency_dag.return_value = self._chain_dag()
        svc = _make_service(dependency_service=dependency_service)

        pkg_a = self._pkg("A")
        pkg_b = self._pkg("B")
        report = svc.analyze_reverse_dependencies(
            [pkg_a, pkg_b], [pkg_a, pkg_b, self._pkg("C")], "main"
        )

        by_name = {entry.name: entry for entry in report.entries}
        assert set(by_name) == {"B", "C"}
        assert by_name["B"].in_workspace is True
        assert by_name["C"].in_workspace is False
        assert by_name["B"].depth == 1
        assert by_name["C"].depth == 2
        assert [entry.name for entry in report.missing] == ["C"]
        assert [entry.name for entry in report.in_workspace] == ["B"]

    def test_dedupes_dependents_across_workspace_packages(self):
        dependency_service = Mock(spec=DependencyService)
        dependency_service.build_dependency_dag.return_value = self._chain_dag()
        svc = _make_service(dependency_service=dependency_service)

        pkg_a = self._pkg("A")
        pkg_b = self._pkg("B")
        # A and B both have C as a transitive dependent; it must appear once.
        report = svc.analyze_reverse_dependencies(
            [pkg_a, pkg_b], [pkg_a, pkg_b], "main"
        )

        assert [entry.name for entry in report.entries].count("C") == 1

    def test_empty_dag_returns_empty_report(self):
        dependency_service = Mock(spec=DependencyService)
        dependency_service.build_dependency_dag.return_value = DependencyGraph(nodes={})
        svc = _make_service(dependency_service=dependency_service)

        report = svc.analyze_reverse_dependencies(
            [self._pkg("A")], [self._pkg("A")], "main"
        )

        assert report.entries == []


class TestPostDagStatusesMissingDependencies:
    def test_missing_dependencies_forwarded_as_extra_description(self):
        proj_a = Mock()
        node_a = _node("A", status=DAGNodeStatus.SUCCESS, project=proj_a, commit_sha="sha-a")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        svc.post_dag_statuses(
            dag, _workspace(), scheduling_complete=True,
            missing_dependencies=["ext-b", "ext-a"],
        )

        args = commit_svc.post_workspace_status.call_args[0]
        assert args == (
            [node_a], WorkspaceStatus.SUCCESS, "main", "build deps not in workspace: ext-a, ext-b"
        )

    def test_no_missing_dependencies_posts_without_extra_description(self):
        proj_a = Mock()
        node_a = _node("A", status=DAGNodeStatus.SUCCESS, project=proj_a, commit_sha="sha-a")
        dag = DependencyGraph(nodes={"A": node_a})

        commit_svc = Mock(spec=CommitStatusService)
        svc = _make_service(commit_status_service=commit_svc)

        svc.post_dag_statuses(dag, _workspace(), scheduling_complete=True)

        commit_svc.post_workspace_status.assert_called_once_with(
            [node_a], WorkspaceStatus.SUCCESS, "main", None
        )
