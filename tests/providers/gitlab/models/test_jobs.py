# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lichoscli.core.models.dag import WorkspaceStatus
from lichoscli.core.models.pipeline_status import PipelineStatus
from lichoscli.providers.gitlab.models.jobs import GitLabJobs
from lichoscli.utils.constants import CI_WORKSPACE_JOB_NAME


def _jobs(job_statuses, workspace_status=None, allow_failure=()):
    statuses = [
        SimpleNamespace(name="job{0}".format(i), status=s, allow_failure=i in allow_failure)
        for i, s in enumerate(job_statuses)
    ]
    if workspace_status:
        statuses.append(SimpleNamespace(name=CI_WORKSPACE_JOB_NAME, status=workspace_status, allow_failure=False))
    project = Mock()
    project.commits.get.return_value.statuses.list.return_value = statuses
    return GitLabJobs(Mock(ref="main", sha="abc", id=1), project)


@pytest.mark.parametrize(
    "jobs, workspace_status, allow_failure, expected",
    [
        (["success", "success"], None, (), PipelineStatus.SUCCESS),
        (["success", "running"], None, (), PipelineStatus.RUNNING),
        (["success", "created"], None, (), PipelineStatus.PENDING),
        (["success", "failed"], None, (), PipelineStatus.FAILED),
        (["success", "failed"], None, (1,), PipelineStatus.SUCCESS),
        (["success", "canceled"], None, (), PipelineStatus.CANCELED),
        (["success", "manual", "skipped"], None, (), PipelineStatus.SUCCESS),
        (["success"], "running", (), PipelineStatus.SUCCESS),
        (["success"], "failed", (), PipelineStatus.SUCCESS),
        (["manual"], None, (), PipelineStatus.MANUAL),
    ],
)
def test_aggregate_status(jobs, workspace_status, allow_failure, expected):
    assert _jobs(jobs, workspace_status, allow_failure).aggregate_status() == expected


def test_aggregate_status_without_jobs_returns_none():
    assert _jobs([]).aggregate_status() is None


@pytest.mark.parametrize(
    "workspace_status, expected",
    [
        ("running", WorkspaceStatus.BUILDING),
        ("canceled", WorkspaceStatus.STALE),
        (None, None),
    ],
)
def test_workspace_status(workspace_status, expected):
    assert _jobs(["success"], workspace_status).workspace_status() == expected
