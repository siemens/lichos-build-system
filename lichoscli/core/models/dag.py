from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional
from .pipeline_status import PipelineStatus

if TYPE_CHECKING:
    from lichoscli.core.models.project import Project
    from .build import BuildInfo


@dataclass
class DependencyGraph:
    """representation of a directed acyclic graph (DAG) for project dependencies."""

    nodes: dict[str, "DAGNode"]

    def add_node(self, node: "DAGNode") -> None:
        """Add a node to the DAG."""
        self.nodes[node.package] = node

    def get_node(self, package: str) -> Optional["DAGNode"]:
        """Retrieve a node by package name."""
        return self.nodes.get(package)

    def remove_node(self, package: str) -> None:
        """Remove a node from the DAG."""
        if package in self.nodes:
            del self.nodes[package]

    def get_build_order(self) -> list[str]:
        """
        Get the optimal build order for packages based on dependency DAG.

        Returns:
            List of package names in build order (dependencies first)
        """
        return self.topological_sort()

    def topological_sort(self) -> list[str]:
        """
        Perform topological sort on the dependency DAG using Kahn's algorithm.

        Returns:
            List of package names in topologically sorted order
        """
        in_degree = {}
        for package_name in self.nodes:
            in_degree[package_name] = 0

        for package_name, node in self.nodes.items():
            for _ in node.direct_dependencies:
                in_degree[package_name] += 1

        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        result = []

        while queue:
            current = queue.popleft()
            result.append(current)

            current_node = self.nodes[current]
            for dependent_name in current_node.reverse_dependencies:
                in_degree[dependent_name] -= 1

                if in_degree[dependent_name] == 0:
                    queue.append(dependent_name)

        if len(result) != len(self.nodes):
            remaining = set(self.nodes.keys()) - set(result)
            result.extend(remaining)

        return result

    def get_transitive_dependents(self, package_name: str) -> list["DAGNode"]:
        """Get all packages that transitively depend on the given package."""
        dependent_nodes = {}
        to_visit = [package_name]
        visited = set()

        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)

            if current in self.nodes:
                node = self.nodes[current]
                for dependent_name in node.reverse_dependencies:
                    if dependent_name not in visited and dependent_name in self.nodes:
                        dependent_nodes[dependent_name] = self.nodes[dependent_name]
                        to_visit.append(dependent_name)

        return list(dependent_nodes.values())

    def calculate_build_levels(self, nodes_to_include: Optional[list["DAGNode"]] = None) -> dict[int, list["DAGNode"]]:
        """
        Calculate build levels ensuring dependencies are built before dependents.

        Args:
            nodes_to_include: Specific DAGNodes to include (defaults to all nodes in the DAG)

        Returns:
            Dictionary mapping levels to lists of DAGNodes to build at that level
        """
        nodes = nodes_to_include if nodes_to_include is not None else list(self.nodes.values())

        node_depths = {}
        memo = {}

        for node in nodes:
            if node.package in self.nodes:
                node_depths[node.package] = self._calculate_package_depth(node.package, memo)
            else:
                node_depths[node.package] = 0

        levels = {}
        for node in nodes:
            depth = node_depths[node.package]
            if depth not in levels:
                levels[depth] = []
            levels[depth].append(node)

        return levels

    def calculate_build_levels_by_name(self, package_names: Optional[list[str]] = None) -> dict[int, list[str]]:
        """
        Calculate build levels by package names (legacy interface).

        Args:
            package_names: Specific package names to include (defaults to all)

        Returns:
            Dictionary mapping levels to lists of package names to build at that level
        """
        if package_names is None:
            nodes_to_include = None
        else:
            nodes_to_include = []
            for package_name in package_names:
                if package_name in self.nodes:
                    nodes_to_include.append(self.nodes[package_name])

        levels_by_node = self.calculate_build_levels(nodes_to_include)

        levels_by_name = {}
        for depth, nodes in levels_by_node.items():
            levels_by_name[depth] = [node.package for node in nodes]

        return levels_by_name

    def _calculate_package_depth(self, package_name: str, memo: dict[str, int]) -> int:
        """Calculate the dependency depth of a package (memoized)."""
        if package_name in memo:
            return memo[package_name]

        if package_name not in self.nodes:
            memo[package_name] = 0
            return 0

        node = self.nodes[package_name]
        if not node.direct_dependencies:
            memo[package_name] = 0
            return 0

        max_depth = 0
        for direct_dependency in node.direct_dependencies:
            dep_depth = self._calculate_package_depth(direct_dependency, memo)
            max_depth = max(max_depth, dep_depth + 1)

        memo[package_name] = max_depth
        return max_depth

    def get_packages_by_status(self, status: str) -> list[str]:
        """Get list of package names with the specified status."""
        return [name for name, node in self.nodes.items() if node.status == status]

    def get_nodes_by_status(self, status: "DAGNodeStatus") -> list["DAGNode"]:
        """Get list of DAGNodes with the specified status."""
        return [node for node in self.nodes.values() if node.status == status]

    def calculate_node_depth(self, node: "DAGNode") -> int:
        """
        Calculate the dependency depth for a single DAGNode.

        Args:
            node: The DAGNode to calculate depth for

        Returns:
            Integer representing the dependency depth of the node
        """
        return self._calculate_package_depth(node.package, {})

    def get_reverse_deps(self, package_name: str) -> list["DAGNode"]:
        """
        Get reverse dependencies for a package using the DAG structure.

        This method extracts transitive dependents from the DAG and returns
        the DAGNode objects representing packages that depend on the input package.

        Args:
            package_name: The package name to find reverse dependencies for

        Returns:
            List of DAGNodes representing packages that depend on the input package
        """
        if package_name not in self.nodes:
            return []

        transitive_dependents = self.get_transitive_dependents(package_name)
        return list(transitive_dependents)

    def find_source_for_binary(self, binary_package_name: str) -> Optional[str]:
        """
        Find the source package name that provides a given binary package.

        Args:
            binary_package_name: The binary package to search for

        Returns:
            Source package name if found, None otherwise
        """
        for source_package_name, node in self.nodes.items():
            if node.provides_binary_package(binary_package_name):
                return source_package_name
        return None

    def to_dict(self) -> dict:
        """Convert the DAG to a dictionary for serialization."""
        return {
            "nodes": {
                name: {
                    "package": node.package,
                    "version": node.version,
                    "architecture": node.architecture,
                    "status": node.status.value,
                    "commit_sha": node.commit_sha,
                    "reverse_dependencies": list(node.reverse_dependencies.keys()),
                    "direct_dependencies": list(node.direct_dependencies.keys()),
                }
                for name, node in self.nodes.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyGraph":
        """Create a DAG from a dictionary."""
        nodes = {}

        for name, node_data in data["nodes"].items():
            node = DAGNode(
                package=node_data["package"],
                version=node_data["version"],
                architecture=node_data["architecture"],
                reverse_dependencies={},
                direct_dependencies={},
                status=DAGNodeStatus(node_data["status"]),
                commit_sha=node_data.get("commit_sha"),
            )
            nodes[name] = node

        for name, node_data in data["nodes"].items():
            node = nodes[name]
            for dep_name in node_data["reverse_dependencies"]:
                if dep_name in nodes:
                    node.reverse_dependencies[dep_name] = nodes[dep_name]
            for dep_name in node_data["direct_dependencies"]:
                if dep_name in nodes:
                    node.direct_dependencies[dep_name] = nodes[dep_name]

        return cls(nodes=nodes)


class DAGNodeStatus(Enum):
    """Status enumeration for DAG nodes."""

    PENDING = "pending"
    BUILDING = "building"
    SUCCESS = "success"
    FAILED = "failed"

    @classmethod
    def from_pipeline_status(cls, pipeline_status: "PipelineStatus") -> "DAGNodeStatus":
        
        if pipeline_status in {
            PipelineStatus.CREATED,
            PipelineStatus.WAITING_FOR_RESOURCE,
            PipelineStatus.PREPARING,
            PipelineStatus.PENDING,
            PipelineStatus.SCHEDULED,
        }:
            return cls.PENDING
        
        if pipeline_status in {PipelineStatus.RUNNING, PipelineStatus.MANUAL}:
            return cls.BUILDING
        
        if pipeline_status == PipelineStatus.SUCCESS:
            return cls.SUCCESS
        
        if pipeline_status in {
            PipelineStatus.FAILED,
            PipelineStatus.CANCELED,
            PipelineStatus.CANCELING,
            PipelineStatus.SKIPPED,
        }:
            return cls.FAILED
        
        return cls.PENDING


@dataclass
class DAGNode:
    """A node in the DAG representing a package and its reverse dependencies."""

    package: str
    version: str
    architecture: str
    reverse_dependencies: dict[str, "DAGNode"]
    direct_dependencies: dict[str, "DAGNode"]
    project: Optional["Project"] = None
    status: DAGNodeStatus = DAGNodeStatus.PENDING
    buildinfo: Optional["BuildInfo"] = None
    commit_sha: Optional[str] = None

    def add_dependent(self, node: "DAGNode") -> None:
        """Add a dependent node."""
        self.reverse_dependencies[node.package] = node

    def add_dependency(self, node: "DAGNode") -> None:
        """Add a dependency node."""
        self.direct_dependencies[node.package] = node

    @property
    def binary_packages(self) -> list[str]:
        """Get list of binary packages produced by this source package."""
        if not self.buildinfo or not self.buildinfo.binary:
            return []
        return list(self.buildinfo.binary)

    def provides_binary_package(self, binary_package_name: str) -> bool:
        """Check if this node provides a specific binary package."""
        return binary_package_name in self.binary_packages

    def set_status(self, new_status: "DAGNodeStatus") -> None:
        self.status = new_status
