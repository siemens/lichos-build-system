# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab dependency service implementation."""

import logging
import os
from typing import TYPE_CHECKING

from gitlab import GitlabError
from packaging import version

from lichoscli.core.models import (
    BuildDependency,
    DAGNode,
    DAGNodeStatus,
    DependencyGraph,
    Project,
)
from lichoscli.core.services import DependencyService, VersionCheckResult
from lichoscli.utils.build import BuildUtils

if TYPE_CHECKING:
    from lichoscli.core.services import BuildInfoService

logger = logging.getLogger(__name__)


class GitLabDependencyService(DependencyService):
    """GitLab implementation of dependency management operations."""

    def __init__(self, buildinfo_service: "BuildInfoService"):
        """Initialize the GitLab dependency service."""
        self._buildinfo_service = buildinfo_service

    def fetch_build_dependencies(
        self,
        package: Project,
        branch: str | None = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> list[BuildDependency]:
        """Get forward dependencies (build dependencies) for a package."""

        if architecture is None:
            architecture = BuildUtils.normalize_architecture(os.uname().machine)

        buildinfo = self._buildinfo_service.get_buildinfo(package, branch, wait_for_completion, architecture)
        if not buildinfo or not buildinfo.installed_build_depends:
            return []

        dependencies = list(buildinfo.installed_build_depends.values())
        return dependencies

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
        buildinfo = self._buildinfo_service.get_buildinfo(project, branch, wait_for_completion)
        if not buildinfo:
            return False
        return buildinfo.has_build_dependency(dependency_package)

    def project_depends_on_project(
        self,
        dependent_project: Project,
        target_project: Project,
        branch: str = None,
        wait_for_completion: bool = True,
    ) -> bool:
        """
        Check if one project depends on another project.

        This implements the same logic as the original Project.project_is_build_depends method
        but through the service layer for better separation of concerns.

        Args:
            dependent_project: The project that might have dependencies
            target_project: The project that might be depended upon
            branch: The branch to check. If None, uses project.default_branch
            wait_for_completion: Whether to wait for pipeline completion

        Returns:
            True if dependent_project depends on target_project, False otherwise
        """
        dependent_buildinfo = self._buildinfo_service.get_buildinfo(dependent_project, branch, wait_for_completion)
        target_buildinfo = self._buildinfo_service.get_buildinfo(target_project, branch, wait_for_completion)

        if not dependent_buildinfo or not dependent_buildinfo.installed_build_depends:
            return False
        if not target_buildinfo or not target_buildinfo.binary:
            logger.debug(
                "Target project %s has no buildinfo or binary packages",
                target_project.name,
            )
            return False

        for binary_package in target_buildinfo.binary:
            if dependent_buildinfo.has_build_dependency(binary_package):
                return True
        return False

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
        dag: DependencyGraph
    ) -> list[VersionCheckResult]:
        """
        Check dependency versions for all packages using the DAG for optimization.

        This method leverages the pre-built DAG to efficiently check all dependency
        relationships without redundant buildinfo fetches or dependency lookups.
        Uses embedded project references from DAG nodes instead of external lookups.
        """

        results = []

        for package_name, node in dag.nodes.items():
            target_package = node.project
            if not target_package:
                continue

            target_buildinfo = node.buildinfo
            if not target_buildinfo or not target_buildinfo.version:
                continue

            target_version = target_buildinfo.version
            target_binary_packages = target_buildinfo.binary or []

            if not target_binary_packages:
                continue

            for dependent_name in node.reverse_dependencies:
                dependent_node = dag.nodes.get(dependent_name)
                if not dependent_node or not dependent_node.buildinfo or not dependent_node.project:
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
        if architecture is None:
            architecture = "arm64"

        logger.info(
            "Building dependency DAG for %d packages on branch %s (wait_for_completion=%s, architecture=%s)",
            len(all_packages),
            branch or "default",
            wait_for_completion,
            architecture,
        )

        buildinfo_map = self._buildinfo_service.get_buildinfo_bulk(
            all_packages, branch, wait_for_completion, architecture
        )

        nodes: dict[str, DAGNode] = {}
        dag = DependencyGraph(nodes={})

        for package in all_packages:
            result = buildinfo_map.get(package.id)
            if not result or not result.buildinfo:
                logger.debug("No buildinfo for package %s, skipping node creation", package.name)
                continue
            buildinfo = result.buildinfo
            cached_pipeline = result.pipeline
            if not buildinfo:
                logger.debug("No buildinfo for package %s, skipping node creation", package.name)
                continue
            pkg_version = buildinfo.version if buildinfo else "unknown"
            target_branch = branch if branch else package.default_branch
            commit_sha = package.get_latest_commit_sha(target_branch)

            node_status = DAGNodeStatus.PENDING
            try:
                latest_pipeline = package.pipelines.get_latest(target_branch, use_cache=True)
                if not latest_pipeline:
                    latest_pipeline = cached_pipeline
                if latest_pipeline:
                    node_status = DAGNodeStatus.from_pipeline_status(latest_pipeline.status)
            except GitlabError as e:
                logger.debug("Could not get pipeline status for %s: %s", package.name, e)

            node = DAGNode(
                package=package.name,
                version=pkg_version,
                architecture="all",
                reverse_dependencies={},
                direct_dependencies={},
                status=node_status,
                buildinfo=buildinfo,
                commit_sha=commit_sha,
                project=package,
            )
            nodes[package.name] = node
            dag.add_node(node)

        for dependent_node in nodes.values():
            dependent_package = dependent_node.project
            if not dependent_package:
                continue

            build_dependencies = list(dependent_node.buildinfo.installed_build_depends.values())
            # we search the name of the source package for each of the deps found in buildinfo installed deps
            for build_dep in build_dependencies:
                source_package_name = None

                if build_dep.package_name in nodes:
                    source_package_name = build_dep.package_name
                else:
                    source_package_name = dag.find_source_for_binary(build_dep.package_name)

                if source_package_name:
                    dependency_node = nodes[source_package_name]
                    dependent_node.add_dependency(dependency_node)
                    dependency_node.add_dependent(dependent_node)
                    logger.debug(
                        "Added dependency: %s depends on %s (via binary package %s)",
                        dependent_package.name,
                        source_package_name,
                        build_dep.package_name,
                    )

        logger.info("Built DAG with %d nodes and dependency relationships", len(nodes))
        return dag

    def get_dag_changed_packages(self, old_dag: DependencyGraph, new_dag: DependencyGraph) -> dict[str, tuple]:
        """Get packages with changed commits between two DAG states."""
        changed_packages = {}

        for package_name in set(old_dag.nodes.keys()) & set(new_dag.nodes.keys()):
            old_node = old_dag.nodes[package_name]
            new_node = new_dag.nodes[package_name]

            old_commit = old_node.commit_sha
            new_commit = new_node.commit_sha

            if old_commit != new_commit:
                changed_packages[package_name] = (new_node.project, old_commit, new_commit)

        for package_name in set(new_dag.nodes.keys()) - set(old_dag.nodes.keys()):
            new_node = new_dag.nodes[package_name]
            if new_node.commit_sha and new_node.project:
                changed_packages[package_name] = (new_node.project, None, new_node.commit_sha)

        return changed_packages

    def has_dag_state_changed(self, old_dag: DependencyGraph, new_dag: DependencyGraph) -> bool:
        """
        Check if the DAG state has changed in a meaningful way.

        This checks for changes in:
        1. Number of packages in the graph
        2. Dependencies between packages (direct and reverse)
        3. Commit hashes of each package
        4. Status of each package (derived from pipeline status)

        Args:
            old_dag: Previous DAG state
            new_dag: Current DAG state

        Returns:
            True if the graph state has changed, False otherwise
        """
        # Check if number of packages changed
        if len(old_dag.nodes) != len(new_dag.nodes):
            logger.info("DAG state changed: number of packages differs (%d vs %d)",
                       len(old_dag.nodes), len(new_dag.nodes))
            return True

        # Check if package set changed
        old_packages = set(old_dag.nodes.keys())
        new_packages = set(new_dag.nodes.keys())
        if old_packages != new_packages:
            added = new_packages - old_packages
            removed = old_packages - new_packages
            logger.info("DAG state changed: package set differs (added: %s, removed: %s)",
                       added, removed)
            return True

        # Check each package for changes in commit hash, dependencies, or status
        for package_name in old_packages:
            old_node = old_dag.nodes[package_name]
            new_node = new_dag.nodes[package_name]

            # Check if commit hash changed
            if old_node.commit_sha != new_node.commit_sha:
                logger.info("DAG state changed: %s commit changed (%s -> %s)",
                           package_name, old_node.commit_sha, new_node.commit_sha)
                return True

            old_deps = set(old_node.direct_dependencies.keys())
            new_deps = set(new_node.direct_dependencies.keys())
            if old_deps != new_deps:
                logger.info("DAG state changed: %s dependencies changed", package_name)
                return True

            old_rev_deps = set(old_node.reverse_dependencies.keys())
            new_rev_deps = set(new_node.reverse_dependencies.keys())
            if old_rev_deps != new_rev_deps:
                logger.info("DAG state changed: %s reverse dependencies changed", package_name)
                return True

            if old_node.status != new_node.status:
                logger.info("DAG state changed: %s status changed (%s -> %s)",
                           package_name, old_node.status.value, new_node.status.value)
                return True

        logger.info("DAG state unchanged: no differences detected")
        return False
