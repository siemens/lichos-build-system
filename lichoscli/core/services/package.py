# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import Optional

from ..models import Project, Projects


class PackageService(ABC):
    """Abstract interface for package management operations."""

    @abstractmethod
    def get_projects(self) -> "Projects":
        """Get the projects collection for this service's group."""

    @abstractmethod
    def get_package(self, package_name: str) -> Optional[Project]:
        """Get a package by name."""

    @abstractmethod
    def get_all_packages(self) -> list[Project]:
        """Get all packages in the group."""

    @abstractmethod
    def get_packages_by_branch(self, branch: str) -> list[Project]:
        """Get all packages that have the specified branch as their default branch."""

    @abstractmethod
    def create_package(
        self,
        name: str,
        branch: str,
        package_type: str,
        subgroup: str,
        access_level: str = "enabled",
    ) -> Optional[Project]:
        """Create a new package."""

    @abstractmethod
    def update_package(
        self,
        package_name: str,
        ci_config_path: Optional[str] = None,
        branch: Optional[str] = None,
        access_level: str = "enabled",
    ) -> Optional[Project]:
        """Update package configuration."""

    @abstractmethod
    def get_package_branch(self, package: Project, branch: str):
        """Get a specific branch from a package."""

    @abstractmethod
    def pretty_format_ci_path(self, package: Project) -> str:
        """Format CI configuration path for display.

        Args:
            package: The package project to format CI path for

        Returns:
            A formatted string representation of the CI path for display
        """

    @abstractmethod
    def get_display_name(self, package: Project) -> str:
        """Get display name for a package with subgroup prefix when applicable.

        Args:
            package: The package project to get display name for

        Returns:
            Display name with subgroup prefix when the package is in a subgroup
        """

    @abstractmethod
    def get_project_by_url(self, url: str) -> Optional[Project]:
        """Resolve a project from a full web URL."""
