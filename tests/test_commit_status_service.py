# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from gitlab import GitlabError

from lichoscli.core.models.dag import DAGNode, WorkspaceStatus
from lichoscli.core.services.commit_status import CommitNodeStatus
from lichoscli.providers.gitlab.services.commit_status_service import (
    GitLabCommitStatusService,
)


def _project(project_id="p1"):
    project = Mock()
    project.id = project_id
    return project


def _nodes(project):
    return [DAGNode(package="A", version="1.0", architecture="amd64", project=project, commit_sha="sha-a")]


def _created_payload(project):
    return project._project.commits.get.return_value.statuses.create.call_args[0][0]


def _pipeline_status(name, status, pipeline_id=123):
    pipeline_status = Mock()
    pipeline_status.name = name
    pipeline_status.status = status
    pipeline_status.pipeline_id = pipeline_id
    return pipeline_status


def _statuses(project, *statuses):
    project._project.commits.get.return_value.statuses.list.return_value = list(
        statuses
    )


def test_workspace_status_appends_extra_description():
    project = _project()
    svc = GitLabCommitStatusService()

    svc.post_workspace_status(
        _nodes(project),
        WorkspaceStatus.SUCCESS,
        "feature/x",
        "build deps not in workspace: ext-a, ext-b",
    )

    payload = _created_payload(project)
    assert payload["state"] == "success"
    assert payload["name"] == "workspace-scheduling"
    assert payload["pipeline_id"] == project.pipelines.get_latest.return_value.id
    assert "ref" not in payload
    assert "workspace build succeeded" in payload["description"]
    assert "build deps not in workspace: ext-a, ext-b" in payload["description"]


def test_workspace_status_is_not_posted_without_a_pipeline_on_the_branch():
    """The scheduler must never make GitLab create a jobless pipeline for its status."""
    project = _project()
    project.pipelines.get_latest.return_value = None

    GitLabCommitStatusService().post_workspace_status(_nodes(project), WorkspaceStatus.SUCCESS, "feature/x")

    project._project.commits.get.return_value.statuses.create.assert_not_called()


def test_workspace_status_without_extra_description():
    project = _project()
    svc = GitLabCommitStatusService()

    svc.post_workspace_status(_nodes(project), WorkspaceStatus.SUCCESS, "feature/x")

    payload = _created_payload(project)
    assert payload["description"] == "workspace build succeeded"


def test_workspace_status_truncates_long_description():
    project = _project()
    svc = GitLabCommitStatusService()

    long_note = "build deps not in workspace: " + ", ".join(
        "pkg-{0}".format(i) for i in range(100)
    )
    svc.post_workspace_status(
        _nodes(project), WorkspaceStatus.STALE, "feature/x", long_note
    )

    payload = _created_payload(project)
    assert len(payload["description"]) <= 255


def test_running_workspace_status_with_final_jobs_is_orphaned():
    """Cleanup must recognize a pipeline whose workspace status alone is running."""
    project = _project()
    _statuses(
        project,
        _pipeline_status("workspace-scheduling", "running"),
        _pipeline_status("build", "success"),
        _pipeline_status("publish", "failed"),
    )
    service = GitLabCommitStatusService()

    result = service.is_pipeline_orphaned(project, "sha-a", 123)

    assert result
    project._project.commits.get.return_value.statuses.list.assert_called_once_with(
        pipeline_id=123,
        order_by="id",
        sort="desc",
        get_all=True,
    )


def test_running_ci_job_keeps_the_pipeline_non_orphaned():
    """Cleanup must preserve a pipeline while any non-workspace status is unfinished."""
    project = _project()
    _statuses(
        project,
        _pipeline_status("workspace-scheduling", "running"),
        _pipeline_status("build", "running"),
    )
    service = GitLabCommitStatusService()

    assert not service.is_pipeline_orphaned(project, "sha-a", 123)


def test_canceling_ci_job_keeps_the_pipeline_non_orphaned():
    """Cleanup must preserve a pipeline while any non-workspace status is canceling."""
    project = _project()
    _statuses(
        project,
        _pipeline_status("workspace-scheduling", "running"),
        _pipeline_status("build", "canceling"),
    )
    service = GitLabCommitStatusService()

    assert not service.is_pipeline_orphaned(project, "sha-a", 123)


def test_final_workspace_status_keeps_the_pipeline_non_orphaned():
    """Cleanup must reject a pipeline whose workspace status is already final."""
    project = _project()
    _statuses(
        project,
        _pipeline_status("workspace-scheduling", "success"),
        _pipeline_status("build", "success"),
    )
    service = GitLabCommitStatusService()

    assert not service.is_pipeline_orphaned(project, "sha-a", 123)


def test_pipeline_without_workspace_status_is_not_orphaned():
    """Cleanup must preserve a pipeline that has no workspace status."""
    project = _project()
    _statuses(project, _pipeline_status("build", "success"))
    service = GitLabCommitStatusService()

    assert not service.is_pipeline_orphaned(project, "sha-a", 123)


def test_workspace_status_from_another_pipeline_is_not_accepted():
    """Orphan detection must not borrow a workspace status from another pipeline."""
    project = _project()
    _statuses(
        project,
        _pipeline_status("workspace-scheduling", "running", pipeline_id=456),
    )
    service = GitLabCommitStatusService()

    assert not service.is_pipeline_orphaned(project, "sha-a", 123)


def test_unreadable_workspace_status_is_never_treated_as_running():
    """Orphan detection must fail safely when GitLab status state cannot be read."""
    project = _project()
    project._project.commits.get.return_value.statuses.list.side_effect = GitlabError(
        "unavailable"
    )
    service = GitLabCommitStatusService()

    assert not service.is_pipeline_orphaned(project, "sha-a", 123)


def test_node_status_is_scoped_to_its_pipeline():
    """Status reporting must identify the exact pipeline sharing a commit SHA."""
    project = _project()
    service = GitLabCommitStatusService()

    service.post_node_status(
        project,
        "sha-a",
        CommitNodeStatus.CANCELLED,
        123,
        "https://example.com/pipelines/123",
    )

    payload = _created_payload(project)
    assert payload["pipeline_id"] == 123


def test_same_status_on_same_commit_is_posted_for_each_pipeline():
    """Status deduplication must keep same-commit pipelines independent."""
    project = _project()
    service = GitLabCommitStatusService()

    service.post_node_status(project, "sha-a", CommitNodeStatus.CANCELLED, 123)
    service.post_node_status(project, "sha-a", CommitNodeStatus.CANCELLED, 456)

    calls = project._project.commits.get.return_value.statuses.create.call_args_list
    assert [call.args[0]["pipeline_id"] for call in calls] == [123, 456]
