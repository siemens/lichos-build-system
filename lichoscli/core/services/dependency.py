# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import NamedTuple

from ..models import BuildDependency, DependencyGraph, Project


class VersionCheckResult(NamedTuple):
    """Result of version check for a dependency."""

    dependent_package: str
    dependent_version: str
    used_version: str
    expected_version: str
    is_correct: bool
    binary_package: str
    source_package: str


class DependencyService(ABC):
    """Abstract interface for dependency management operations."""

    @abstractmethod
    def fetch_build_dependencies(
        self,
        package: Project,
        branch: str | None = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> list[BuildDependency]:
        """Get forward dependencies (build dependencies) for a package."""

    @abstractmethod
    def has_build_dependency(
        self,
        project: Project,
        dependency_package: str,
        branch: str = None,
        wait_for_completion: bool = True,
    ) -> bool:
        """
        Check if project has a specific build dependency.

        Args:
            project: The project to check
            dependency_package: The package name to check for
            branch: The branch to check. If None, uses project.default_branch
            wait_for_completion: Whether to wait for pipeline completion

        Returns:
            True if project depends on the package, False otherwise
        """

    @abstractmethod
    def project_depends_on_project(
        self,
        dependent_project: Project,
        target_project: Project,
        branch: str = None,
        wait_for_completion: bool = True,
    ) -> bool:
        """
        Check if one project depends on another project.

        Args:
            dependent_project: The project that might have dependencies
            target_project: The project that might be depended upon
            branch: The branch to check. If None, uses project.default_branch
            wait_for_completion: Whether to wait for pipeline completion

        Returns:
            True if dependent_project depends on target_project, False otherwise
        """

    @abstractmethod
    def compare_versions(self, version1: str, version2: str) -> bool:
        """
        Compare if two versions are equivalent.

        Args:
            version1: First version string
            version2: Second version string

        Returns:
            True if versions are equivalent, False otherwise
        """

    @abstractmethod
    def normalize_version(self, version_string: str) -> str:
        """
        Normalize a version string by removing epoch and debian revision.

        Args:
            version_string: Version string to normalize

        Returns:
            Normalized version string
        """

    @abstractmethod
    def check_all_dependency_versions_from_dag(
        self,
        dag: DependencyGraph
    ) -> list[VersionCheckResult]:
        """
        Check dependency versions for all packages using the DAG for optimization.

        This method leverages the pre-built DAG to efficiently check all dependency
        relationships without redundant buildinfo fetches or dependency lookups.
        The project references are now embedded directly in DAG nodes.

        Args:
            dag: Pre-built dependency DAG containing all package relationships with embedded projects
            branch: Branch to get buildinfo from. If None, uses default branch
            wait_for_completion: Whether to wait for pipeline completion.

        Returns:
            List of version check results for all dependency relationships in the DAG
        """

    @abstractmethod
    def build_dependency_dag(
        self,
        all_packages: list[Project],
        branch: str | None = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> DependencyGraph:
        """
        Build a directed acyclic graph (DAG) of all package dependencies.

        Args:
            all_packages: All packages to include in the DAG
            branch: Branch to get buildinfo from. If None, uses each package's default branch
            wait_for_completion: Whether to wait for pipeline completion. If False, uses latest available pipeline.
            architecture: Architecture to fetch buildinfo for. If None, uses host architecture.

        Returns:
            DAG representation of all package dependencies
        """

    @abstractmethod
    def get_dag_changed_packages(self, old_dag: DependencyGraph, new_dag: DependencyGraph) -> dict[str, tuple]:
        """
        Get packages with changed commits between two DAG states.

        Args:
            old_dag: Previous DAG state
            new_dag: Current DAG state

        Returns:
            Dict mapping package names to (project, old_commit, new_commit) tuples
            where project has path_with_namespace attribute, old_commit may be None for new packages
        """

    @abstractmethod
    def has_dag_state_changed(self, old_dag: DependencyGraph, new_dag: DependencyGraph) -> bool:
        """
        Check if the DAG state has changed in a meaningful way.

        Compares:
        - Number of packages
        - Dependencies between packages
        - Commit hashes of each package
        - Status of each package (derived from pipeline status)

        Args:
            old_dag: Previous DAG state
            new_dag: Current DAG state

        Returns:
            True if the graph state has changed, False otherwise
        """
