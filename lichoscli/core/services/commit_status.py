# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract commit status service interface for reporting DAG node states to the VCS provider."""

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
    """Abstract interface for posting DAG node build states as VCS commit statuses."""

    @abstractmethod
    def post_node_status(
        self,
        project: "Project",
        commit_sha: str,
        status: CommitNodeStatus,
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
    ) -> None:
        """Post the same workspace-level status to all packages in the workspace."""
        raise NotImplementedError
