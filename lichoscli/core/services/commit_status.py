# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract commit status service for reading and reporting DAG node states."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Optional

from lichoscli.core.models.dag import WorkspaceStatus

if TYPE_CHECKING:
    from lichoscli.core.models.project import Project


class CommitNodeStatus(Enum):
    """Commit status states mapped to VCS provider state strings."""

    CANCELLED = "canceled"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


__all__ = ["CommitNodeStatus", "WorkspaceStatus", "CommitStatusService"]


class CommitStatusService(ABC):
    """Abstract interface for reading and posting DAG node commit statuses."""

    @abstractmethod
    def is_pipeline_orphaned(
        self,
        project: "Project",
        commit_sha: str,
        pipeline_id: int,
    ) -> bool:
        """Return whether only the pipeline's workspace status is unfinished."""
        raise NotImplementedError

    @abstractmethod
    def post_node_status(
        self,
        project: "Project",
        commit_sha: str,
        status: CommitNodeStatus,
        pipeline_id: int,
        pipeline_url: Optional[str] = None,
    ) -> None:
        """Post or update the commit status for a single DAG node."""
        raise NotImplementedError

    @abstractmethod
    def post_workspace_status(
        self,
        nodes: dict[str, "Project"],
        commit_shas: dict[str, str],
        status: "WorkspaceStatus",
        extra_description: Optional[str] = None,
    ) -> None:
        """Post the same workspace-level status to all packages in the workspace.

        ``extra_description`` is appended to the status description for
        informational purposes only and does not affect the reported state.
        """
        raise NotImplementedError
