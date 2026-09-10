# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of CommitStatusService using the GitLab commit statuses API."""

import logging
from typing import TYPE_CHECKING, Optional

from gitlab import GitlabError

from lichoscli.core.models.pipeline_status import PipelineStatus
from lichoscli.core.services.commit_status import (
    CommitNodeStatus,
    CommitStatusService,
    WorkspaceStatus,
)
from lichoscli.utils.constants import CI_WORKSPACE_JOB_NAME

if TYPE_CHECKING:
    from lichoscli.core.models.project import Project

logger = logging.getLogger(__name__)

_MAX_DESCRIPTION_LENGTH = 255

_DESCRIPTIONS = {
    CommitNodeStatus.CANCELLED: "will be rebuilt",
    CommitNodeStatus.RUNNING: "schedule in progress",
    CommitNodeStatus.SUCCESS: "built",
    CommitNodeStatus.FAILED: "build failed",
}

_WORKSPACE_DESCRIPTIONS = {
    WorkspaceStatus.BUILDING: "workspace build in progress",
    WorkspaceStatus.FAILED: "workspace build failed",
    WorkspaceStatus.SUCCESS: "workspace build succeeded",
    WorkspaceStatus.STALE: "workspace needs rebuild",
}


class GitLabCommitStatusService(CommitStatusService):
    """Reads and posts DAG node states as GitLab commit statuses."""

    def __init__(self) -> None:
        self._posted_statuses: set[tuple] = set()

    def is_pipeline_orphaned(
        self,
        project: "Project",
        commit_sha: str,
        pipeline_id: int,
    ) -> bool:
        """Return whether only the pipeline's workspace status is unfinished."""
        try:
            statuses = project._project.commits.get(commit_sha).statuses.list(
                pipeline_id=pipeline_id,
                order_by="id",
                sort="desc",
                get_all=True,
            )
        except GitlabError as exc:
            logger.warning(
                "Failed to read workspace status for project %s pipeline %s: %s",
                project.id,
                pipeline_id,
                exc,
            )
            return False

        if not statuses:
            return False

        if any(status.pipeline_id != pipeline_id for status in statuses):
            return False

        workspace_is_running = any(
            status.name == CI_WORKSPACE_JOB_NAME
            and status.status == WorkspaceStatus.BUILDING.value
            for status in statuses
        )
        final_statuses = frozenset(
            status.value
            for status in PipelineStatus.final_states()
            if status != PipelineStatus.CANCELING
        )
        all_other_statuses_are_final = all(
            status.name == CI_WORKSPACE_JOB_NAME or status.status in final_statuses
            for status in statuses
        )
        return workspace_is_running and all_other_statuses_are_final

    def post_node_status(
        self,
        project: "Project",
        commit_sha: str,
        status: CommitNodeStatus,
        pipeline_id: int,
        pipeline_url: Optional[str] = None,
    ) -> None:
        """Post or update a commit status for a single DAG node on GitLab."""
        description = _DESCRIPTIONS.get(status, "")

        payload = {
            "state": status.value,
            "name": CI_WORKSPACE_JOB_NAME,
            "description": description,
            "pipeline_id": pipeline_id,
        }
        if pipeline_url:
            payload["target_url"] = pipeline_url

        cache_key = (project.id, commit_sha, pipeline_id, status.value)
        if cache_key in self._posted_statuses:
            logger.debug(
                "Skipping duplicate commit status for project %s @ %s",
                project.id,
                commit_sha,
            )
            return

        logger.debug(
            "Posting commit status %s for project %s @ %s (pipeline_url=%s)",
            status.value,
            project.id,
            commit_sha,
            pipeline_url,
        )

        try:
            project._project.commits.get(commit_sha).statuses.create(payload)
            self._posted_statuses.add(cache_key)
        except GitlabError as exc:
            logger.warning(
                "Failed to post commit status %s for project %s @ %s: %s",
                status.value,
                project.id,
                commit_sha,
                exc,
            )

    def post_workspace_status(
        self,
        nodes: dict[str, "Project"],
        commit_shas: dict[str, str],
        status: WorkspaceStatus,
        extra_description: Optional[str] = None,
    ) -> None:
        """Post the same workspace-level status to all packages.

        ``extra_description`` is appended to the status description for
        informational purposes without affecting the reported state.
        """
        description = _WORKSPACE_DESCRIPTIONS.get(status, "")
        if extra_description:
            description = "{0} | {1}".format(description, extra_description)
        if len(description) > _MAX_DESCRIPTION_LENGTH:
            description = description[: _MAX_DESCRIPTION_LENGTH - 1] + "\u2026"

        for package_name, project in nodes.items():
            commit_sha = commit_shas.get(package_name)
            if not commit_sha:
                logger.warning(
                    "Skipping workspace status for %s: missing commit_sha",
                    package_name,
                )
                continue

            cache_key = (project.id, commit_sha, status.value)
            if cache_key in self._posted_statuses:
                logger.debug(
                    "Skipping duplicate workspace status %s for project %s @ %s",
                    status.value,
                    project.id,
                    commit_sha,
                )
                continue

            payload = {
                "state": status.value,
                "name": CI_WORKSPACE_JOB_NAME,
                "description": description,
            }

            logger.debug(
                "Posting workspace status %s for project %s @ %s",
                status.value,
                project.id,
                commit_sha,
            )

            try:
                project._project.commits.get(commit_sha).statuses.create(payload)
                self._posted_statuses.add(cache_key)
            except GitlabError as exc:
                logger.warning(
                    "Failed to post workspace status %s for project %s @ %s: %s",
                    status.value,
                    project.id,
                    commit_sha,
                    exc,
                )
