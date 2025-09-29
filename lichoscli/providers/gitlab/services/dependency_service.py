"""GitLab dependency service implementation."""

import logging
from typing import TYPE_CHECKING, Dict, List

from packaging import version
from rich import box
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from lichoscli.core.models import (
    BuildDependency,
    DAGNode,
    DAGNodeStatus,
    DependencyGraph,
    Project,
)
from lichoscli.core.services import DependencyService, VersionCheckResult

if TYPE_CHECKING:
    from lichoscli.core.services import BuildInfoService

logger = logging.getLogger(__name__)


class GitLabDependencyService(DependencyService):
    """GitLab implementation of dependency management operations."""

    def __init__(self, buildinfo_service: "BuildInfoService"):
        """Initialize the GitLab dependency service."""
        self._buildinfo_service = buildinfo_service

    def get_forward_dependencies(
        self, package: Project, branch: str = None, wait_for_completion: bool = True
    ) -> List[BuildDependency]:
        """Get forward dependencies (build dependencies) for a package."""

        buildinfo = self._buildinfo_service.get_buildinfo(package, branch, wait_for_completion)
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
        dag: DependencyGraph,
        branch: str = None,
        wait_for_completion: bool = True,
    ) -> List[VersionCheckResult]:
        """
        Check dependency versions for all packages using the DAG for optimization.

        This method leverages the pre-built DAG to efficiently check all dependency
        relationships without redundant buildinfo fetches or dependency lookups.
        Uses embedded project references from DAG nodes instead of external lookups.
        """
        logger.info(
            "Checking dependency versions for all packages using DAG optimization (%d packages)",
            len(dag.nodes),
        )

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

        logger.info("Found %d dependency version checks using DAG optimization", len(results))
        return results

    def build_dependency_dag(
        self,
        all_packages: List[Project],
        branch: str = None,
        wait_for_completion: bool = True,
    ) -> DependencyGraph:
        """
        Build a directed acyclic graph (DAG) of all package dependencies.

        Args:
            all_packages: All packages to include in the DAG
            branch: Branch to get buildinfo from. If None, uses each package's default branch
            wait_for_completion: Whether to wait for pipeline completion. If False, uses latest available pipeline.

        Returns:
            DAG representation of all package dependencies
        """
        logger.info(
            "Building dependency DAG for %d packages on branch %s (wait_for_completion=%s)",
            len(all_packages),
            branch or "default",
            wait_for_completion,
        )

        if branch:
            self._buildinfo_service.get_buildinfo_bulk(all_packages, branch, wait_for_completion)
        else:
            self._buildinfo_service.get_buildinfo_bulk(all_packages, wait_for_completion)

        nodes = {}
        dag = DependencyGraph(nodes={})

        for package in all_packages:
            buildinfo = self._buildinfo_service.get_buildinfo(package, branch, wait_for_completion)
            pkg_version = buildinfo.version if buildinfo else "unknown"
            target_branch = branch if branch else package.default_branch
            commit_sha = package.get_latest_commit_sha(target_branch)

            node = DAGNode(
                package=package.name,
                version=pkg_version,
                architecture="all",
                reverse_dependencies={},
                direct_dependencies={},
                status=DAGNodeStatus.PENDING,
                buildinfo=buildinfo,
                commit_sha=commit_sha,
                project=package,
            )
            nodes[package.name] = node
            dag.add_node(node)

        for package in all_packages:
            package_node = nodes[package.name]

            forward_deps = self.get_forward_dependencies(package, branch, wait_for_completion)

            filtered_deps = list(forward_deps)

            for dep in filtered_deps:
                target_source_package = None

                if dep.package in nodes:
                    target_source_package = dep.package
                else:
                    target_source_package = dag.find_source_for_binary(dep.package)

                if target_source_package:
                    dep_node = nodes[target_source_package]
                    package_node.add_dependency(dep_node)
                    dep_node.add_dependent(package_node)
                    logger.debug(
                        "Added dependency: %s depends on %s (via binary package %s)",
                        package.name,
                        target_source_package,
                        dep.package,
                    )

        logger.info("Built DAG with %d nodes and dependency relationships", len(nodes))
        return dag

    def display_dependency_version_verification(
        self, version_check_results: List[VersionCheckResult], console
    ) -> None:
        """Display comprehensive dependency version verification results in a table format."""
        if not version_check_results:
            console.print("\n[dim]No dependency version checks performed[/dim]")
            return

        console.print(
            f"\n[bold blue]Dependency Version Verification ({len(version_check_results)} checks):[/bold blue]"
        )

        results_by_package = {}
        for result in version_check_results:
            if result.dependent_package not in results_by_package:
                results_by_package[result.dependent_package] = []
            results_by_package[result.dependent_package].append(result)

        correct_count = sum(1 for r in version_check_results if r.is_correct)
        incorrect_count = len(version_check_results) - correct_count

        if incorrect_count == 0:
            console.print(f"[green]✓ All {correct_count} dependency version checks passed![/green]")
        else:
            console.print(f"[yellow]⚠ {incorrect_count} version mismatches found, {correct_count} correct[/yellow]")

        table = Table(box=box.ROUNDED, title="Dependency Version Verification Details")
        table.add_column("Dependent Package", style="bold cyan")
        table.add_column("Dependency", style="white")
        table.add_column("Used Version", style="dim")
        table.add_column("Expected Version", style="dim")
        table.add_column("Status", justify="center")

        for package_name in sorted(results_by_package.keys()):
            results = results_by_package[package_name]

            for i, result in enumerate(results):
                pkg_display = package_name if i == 0 else ""

                if result.is_correct:
                    status = "[green]✓ Correct[/green]"
                    used_version_style = "green"
                    expected_version_style = "green"
                else:
                    status = "[red]✗ Mismatch[/red]"
                    used_version_style = "red"
                    expected_version_style = "bold green"

                table.add_row(
                    pkg_display,
                    result.binary_package,
                    f"[{used_version_style}]{result.used_version}[/{used_version_style}]",
                    f"[{expected_version_style}]{result.expected_version}[/{expected_version_style}]",
                    status,
                )

        console.print(table)

        if incorrect_count == 0:
            console.print("\n[bold green]: All packages have correct dependency versions![/bold green]")
        else:
            console.print(
                f"\n[bold yellow]⚠ WARNING: {incorrect_count} packages have outdated dependencies and need rebuilding[/bold yellow]"
            )

    def print_dag_tree(self, dag: DependencyGraph, console) -> None:
        """Print the DAG as a tree structure using Rich library."""
        if not dag.nodes:
            console.print("[dim]Empty DAG[/dim]")
            return

        root_nodes = [node for node in dag.nodes.values() if not node.direct_dependencies]

        if not root_nodes:
            console.print("[yellow]No root nodes found (circular dependency?)[/yellow]")
            root_nodes = list(dag.nodes.values())

        tree = Tree("[bold blue]Package Dependency Tree[/bold blue]")
        visited = set()

        for root in root_nodes:
            self._add_rich_node(tree, root, visited)

        console.print(tree)

    def _add_rich_node(self, parent_tree: Tree, node: DAGNode, visited: set) -> None:
        """Add a node and its dependents to the Rich tree."""
        if node.package in visited:
            circular_text = Text(f"{node.package} ", style="dim")
            circular_text.append("(circular)", style="red italic")
            parent_tree.add(circular_text)
            return

        visited.add(node.package)

        node_text = Text()
        status_color = self._get_status_color(node.status)

        node_text.append(node.package, style=f"bold {status_color}")

        if node.version:
            node_text.append(f" v{node.version}", style="dim cyan")

        current_branch = parent_tree.add(node_text)
        dependents = sorted(node.reverse_dependencies.values(), key=lambda x: x.package)

        for dependent in dependents:
            self._add_rich_node(current_branch, dependent, visited.copy())

    def _get_status_color(self, status) -> str:
        """Get Rich color for build status."""
        status_colors = {
            "pending": "yellow",
            "building": "blue",
            "success": "green",
            "failed": "red",
        }
        status_str = status.value if hasattr(status, "value") else str(status)
        return status_colors.get(status_str.lower(), "white")

    def get_dag_changed_packages(self, old_dag: DependencyGraph, new_dag: DependencyGraph) -> Dict[str, tuple]:
        """Get packages with changed commits between two DAG states."""
        changed_packages = {}

        for package_name in set(old_dag.nodes.keys()) & set(new_dag.nodes.keys()):
            old_node = old_dag.nodes[package_name]
            new_node = new_dag.nodes[package_name]

            old_commit = old_node.commit_sha
            new_commit = new_node.commit_sha

            changed_packages[package_name] = (new_node.project, old_commit, new_commit)

        for package_name in set(new_dag.nodes.keys()) - set(old_dag.nodes.keys()):
            new_node = new_dag.nodes[package_name]
            if new_node.commit_sha and new_node.project:
                changed_packages[package_name] = (new_node.project, None, new_node.commit_sha)

        return changed_packages
