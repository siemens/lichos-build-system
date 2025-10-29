"""Abstract interface for buildinfo management operations."""

from abc import ABC, abstractmethod
from typing import Optional

from ..models import BuildInfo, Project


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
    ) -> dict[int, Optional[BuildInfo]]:
        """
        Get buildinfo for multiple projects efficiently.

        Args:
            projects: List of projects to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch for each project
            wait_for_completion: Whether to wait for pipeline completion. If False, uses latest available pipeline.
            architecture: The architecture to get buildinfo for. If None, uses host architecture.

        Returns:
            Dictionary mapping project ID to BuildInfo (or None if not available)
        """

    @abstractmethod
    def clear_cache(self) -> None:
        """Clear the buildinfo cache."""
