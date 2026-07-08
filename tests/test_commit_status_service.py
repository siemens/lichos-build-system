# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from lichoscli.core.models.dag import WorkspaceStatus
from lichoscli.providers.gitlab.services.commit_status_service import (
    GitLabCommitStatusService,
)


def _project(project_id="p1"):
    project = Mock()
    project.id = project_id
    return project


def _created_payload(project):
    return project._project.commits.get.return_value.statuses.create.call_args[0][0]


def test_workspace_status_appends_extra_description():
    project = _project()
    svc = GitLabCommitStatusService()

    svc.post_workspace_status(
        {"A": project},
        {"A": "sha-a"},
        WorkspaceStatus.SUCCESS,
        "build deps not in workspace: ext-a, ext-b",
    )

    payload = _created_payload(project)
    assert payload["state"] == "success"
    assert payload["name"] == "workspace-scheduling"
    assert "workspace build succeeded" in payload["description"]
    assert "build deps not in workspace: ext-a, ext-b" in payload["description"]


def test_workspace_status_without_extra_description():
    project = _project()
    svc = GitLabCommitStatusService()

    svc.post_workspace_status({"A": project}, {"A": "sha-a"}, WorkspaceStatus.SUCCESS)

    payload = _created_payload(project)
    assert payload["description"] == "workspace build succeeded"


def test_workspace_status_truncates_long_description():
    project = _project()
    svc = GitLabCommitStatusService()

    long_note = "build deps not in workspace: " + ", ".join(
        "pkg-{0}".format(i) for i in range(100)
    )
    svc.post_workspace_status(
        {"A": project}, {"A": "sha-a"}, WorkspaceStatus.STALE, long_note
    )

    payload = _created_payload(project)
    assert len(payload["description"]) <= 255
