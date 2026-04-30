# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
import logging
from typing import NamedTuple

from packaging import version

from ..models import BuildDependency, DependencyGraph, Project

logger = logging.getLogger(__name__)


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

    def compare_versions(self, version1: str, version2: str) -> bool:
        """
        Compare if two versions are equivalent.

        Args:
            version1: First version string
            version2: Second version string

        Returns:
            True if versions are equivalent, False otherwise
        """
        if not version1 or not version2:
            return False

        normalized_v1 = self.normalize_version(version1)
        normalized_v2 = self.normalize_version(version2)

        try:
            return version.parse(normalized_v1) == version.parse(normalized_v2)
        except (version.InvalidVersion, ValueError, TypeError):
            return normalized_v1 == normalized_v2

    def normalize_version(self, version_string: str) -> str:
        """
        Normalize a version string by removing epoch and debian revision.

        Args:
            version_string: Version string to normalize

        Returns:
            Normalized version string
        """
        if not version_string:
            return ""

        if ":" in version_string:
            version_string = version_string.split(":", 1)[1]

        if "-" in version_string:
            version_string = version_string.rsplit("-", 1)[0]
        return version_string

    def check_all_dependency_versions_from_dag(
        self,
        dag: DependencyGraph,
    ) -> list[VersionCheckResult]:
        """ Check dependency versions for all packages using the DAG for optimization."""
        results = []

        for package_name, node in dag.nodes.items():
            target_buildinfo = node.buildinfo
            if not target_buildinfo or not target_buildinfo.version:
                logger.warning(
                    "Missing buildinfo or version for package '%s', skipping version checks for its dependents",
                    package_name,
                )
                continue

            target_version = target_buildinfo.version
            target_binary_packages = target_buildinfo.binary or []

            if not target_binary_packages:
                logger.warning(
                    "No binary packages found for '%s', skipping version checks for its dependents",
                    package_name,
                )
                continue

            for dependent_name in node.reverse_dependencies:
                dependent_node = dag.nodes.get(dependent_name)
                if not dependent_node or not dependent_node.buildinfo:
                    logger.warning(
                        "Missing node or buildinfo for dependent package '%s', skipping version check against '%s'",
                        dependent_name,
                        package_name,
                    )
                    continue

                dependent_buildinfo = dependent_node.buildinfo

                for binary_pkg in target_binary_packages:
                    build_dep = dependent_buildinfo.get_build_dependency(binary_pkg)
                    if build_dep:
                        used_version = build_dep.version
                        is_correct = self.compare_versions(used_version, target_version)

                        results.append(
                            VersionCheckResult(
                                dependent_package=dependent_name,
                                dependent_version=dependent_buildinfo.version or "unknown",
                                used_version=used_version,
                                expected_version=target_version,
                                is_correct=is_correct,
                                binary_package=binary_pkg,
                                source_package=package_name,
                            )
                        )

        return results

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
