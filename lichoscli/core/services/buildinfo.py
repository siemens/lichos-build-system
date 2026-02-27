# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract interface for buildinfo management operations."""

from abc import ABC, abstractmethod
from typing import NamedTuple, Optional

from ..models import BuildInfo, Pipeline, Project


class BuildInfoResult(NamedTuple):
    """Result of a buildinfo lookup for a single project."""

    buildinfo: Optional[BuildInfo] = None
    pipeline: Optional[Pipeline] = None


class BuildInfoService(ABC):
    """Abstract interface for build information management."""

    @abstractmethod
    def get_buildinfo(
        self,
        project: Project,
        branch: str = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> Optional[BuildInfo]:
        """
        Get buildinfo for a single project.

        Args:
            project: The project to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch
            wait_for_completion: Whether to wait for pipeline completion. For workspace
                               creation, this can be False to use get_some_latest_pipeline.
            architecture: The architecture to get buildinfo for. If None, uses host architecture.

        Returns:
            BuildInfo if available, None otherwise
        """

    @abstractmethod
    def get_buildinfo_bulk(
        self,
        projects: list[Project],
        branch: str = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> dict[int, BuildInfoResult]:
        """
        Get buildinfo for multiple projects efficiently.

        Args:
            projects: List of projects to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch for each project
            wait_for_completion: Whether to wait for pipeline completion. If False, uses latest available pipeline.
            architecture: The architecture to get buildinfo for. If None, uses host architecture.

        Returns:
            Dictionary mapping project ID to BuildInfoResult
        """

    @abstractmethod
    def clear_cache(self) -> None:
        """Clear the buildinfo cache."""
