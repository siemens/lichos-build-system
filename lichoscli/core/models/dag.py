# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Optional
from .pipeline_status import PipelineStatus

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from lichoscli.core.services import VersionCheckResult
    from lichoscli.core.models.project import Project
    from .build import BuildInfo


class WorkspaceStatus(Enum):
    """Workspace-level scheduling status posted globally to all packages."""

    BUILDING = "running"
    FAILED = "failed"
    SUCCESS = "success"
    STALE = "canceled"


@dataclass
class DependencyGraph:
    """Directed acyclic graph for package dependency scheduling."""

    nodes: dict[str, "DAGNode"]

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    # ── Node management ──────────────────────────────────────────────

    def add_node(self, node: "DAGNode") -> None:
        self.nodes[node.package] = node

    def get_node(self, package: str) -> Optional["DAGNode"]:
        return self.nodes.get(package)

    def remove_node(self, package: str) -> None:
        """Remove a node and its edges from the graph."""
        node = self.nodes.pop(package, None)
        if node is None:
            return
        for dep in node.direct_dependencies.values():
            dep.reverse_dependencies.pop(package, None)
        for rev in node.reverse_dependencies.values():
            rev.direct_dependencies.pop(package, None)

    # ── Scheduling primitives ────────────────────────────────────────

    def get_ready_nodes(self) -> list["DAGNode"]:
        """
        Return PENDING nodes whose direct dependencies have all succeeded.

        These nodes can be scheduled for building immediately.  Call this
        in a loop to drive maximum-parallelism execution of the graph.
        """
        return [
            node
            for node in self.nodes.values()
            if node.status == DAGNodeStatus.PENDING
            and all(
                dep.status == DAGNodeStatus.SUCCESS
                for dep in node.direct_dependencies.values()
            )
        ]

    def mark_building(self, package_name: str) -> None:
        """Transition a node from PENDING to BUILDING."""
        self.nodes[package_name].set_status(DAGNodeStatus.BUILDING)

    def mark_succeeded(self, package_name: str) -> list["DAGNode"]:
        """
        Transition a node to SUCCESS and return dependents that became ready.

        Enables reactive scheduling: the caller can immediately trigger
        the returned nodes without rescanning the entire graph.
        """
        node = self.nodes[package_name]
        node.set_status(DAGNodeStatus.SUCCESS)
        node.is_stale = False
        return [
            dependent
            for dependent in node.reverse_dependencies.values()
            if dependent.status == DAGNodeStatus.PENDING
            and all(
                dep.status == DAGNodeStatus.SUCCESS
                for dep in dependent.direct_dependencies.values()
            )
        ]

    def mark_failed(self, package_name: str) -> list["DAGNode"]:
        """
        Transition a node to FAILED and return PENDING dependents that are
        now blocked (they can never build in this scheduling run).
        """
        self.nodes[package_name].set_status(DAGNodeStatus.FAILED)
        return self._collect_blocked_dependents(package_name)

    def is_complete(self) -> bool:
        """True when every node has reached a terminal status."""
        return all(node.status.is_terminal for node in self.nodes.values())

    def get_blocked_nodes(self) -> list["DAGNode"]:
        """
        Return PENDING nodes that can never build because a transitive
        dependency has failed.
        """
        failed_packages = [
            name
            for name, node in self.nodes.items()
            if node.status == DAGNodeStatus.FAILED
        ]
        blocked: dict[str, "DAGNode"] = {}
        for pkg in failed_packages:
            for node in self._collect_blocked_dependents(pkg):
                blocked[node.package] = node
        return list(blocked.values())

    # ── Graph queries ────────────────────────────────────────────────

    def get_roots(self) -> list["DAGNode"]:
        """Return nodes with no dependencies (entry points of the graph)."""
        return [
            node
            for node in self.nodes.values()
            if not node.direct_dependencies
        ]

    def topological_order(self) -> list["DAGNode"]:
        """Return nodes with every dependency before its dependents."""
        incoming_edges = {
            name: sum(dep_name in self.nodes for dep_name in node.direct_dependencies)
            for name, node in self.nodes.items()
        }
        dependents: dict[str, list[str]] = {name: [] for name in self.nodes}
        for name, node in self.nodes.items():
            for dependency_name in node.direct_dependencies:
                if dependency_name in dependents:
                    dependents[dependency_name].append(name)

        ready = [name for name in self.nodes if incoming_edges[name] == 0]
        ordered: list[DAGNode] = []
        while ready:
            name = ready.pop(0)
            ordered.append(self.nodes[name])
            for dependent_name in dependents[name]:
                incoming_edges[dependent_name] -= 1
                if incoming_edges[dependent_name] == 0:
                    ready.append(dependent_name)

        if len(ordered) != len(self.nodes):
            raise ValueError("Dependency graph contains a cycle")
        return ordered

    def get_transitive_dependents(self, package_name: str) -> list["DAGNode"]:
        """Get all packages that transitively depend on the given package."""
        return self._traverse_dependents(package_name)

    def find_source_for_binary(self, binary_package_name: str) -> Optional[str]:
        """Find the source package that produces a given binary package."""
        for source_name, node in self.nodes.items():
            if node.provides_binary_package(binary_package_name):
                return source_name
        return None

    def get_nodes_by_status(self, status: "DAGNodeStatus") -> list["DAGNode"]:
        """Return all nodes with the given status."""
        return [node for node in self.nodes.values() if node.status == status]

    def get_depth(
        self,
        package_name: str,
        memo: Optional[dict[str, int]] = None,
    ) -> int:
        """
        Dependency depth of a package: 0 for packages with no in-graph
        dependencies, N for the longest chain of N edges to a root.

        For batch lookups, pass the same ``memo`` dict across calls to avoid
        re-walking the subgraph for each node.
        """
        return self._calculate_depth(package_name, memo if memo is not None else {})

    def group_by_depth(
        self, nodes_to_include: Optional[list["DAGNode"]] = None
    ) -> dict[int, list["DAGNode"]]:
        """
        Group nodes by their structural dependency depth.

        Depth-0 nodes have no in-graph dependencies, depth-1 nodes depend
        only on depth-0 nodes, and so forth.  Useful for display and
        analysis; scheduling should use ``get_ready_nodes`` instead.
        """
        nodes = (
            nodes_to_include
            if nodes_to_include is not None
            else list(self.nodes.values())
        )
        memo: dict[str, int] = {}
        levels: dict[int, list["DAGNode"]] = {}
        for node in nodes:
            depth = self._calculate_depth(node.package, memo)
            levels.setdefault(depth, []).append(node)
        return levels

    def apply_version_check_results(
        self,
        version_check_results: Iterable["VersionCheckResult"],
    ) -> set[str]:
        """Mark nodes as stale when dependency version checks report mismatches."""
        stale_packages = {
            result.dependent_package
            for result in version_check_results
            if not result.is_correct and result.dependent_package in self.nodes
        }

        for node in self.nodes.values():
            node.is_stale = node.package in stale_packages

        return stale_packages

    def get_stale_packages(self) -> set[str]:
        """Return package names currently marked as stale."""
        return {name for name, node in self.nodes.items() if node.is_stale}

    def compute_workspace_status(self) -> "WorkspaceStatus":
        """Derive the global workspace status from all node statuses.

        Rules applied in priority order:
        1. Any node FAILED → FAILED
        2. Any node BUILDING or PENDING (with builds expected) → BUILDING
        3. Any node marked stale → STALE
        4. Otherwise → SUCCESS
        """
        has_failed = False
        has_active = False
        has_stale = False

        for node in self.nodes.values():
            if node.status == DAGNodeStatus.FAILED:
                has_failed = True
            elif node.status in (DAGNodeStatus.BUILDING, DAGNodeStatus.PENDING):
                has_active = True
            if node.is_stale:
                has_stale = True

        if has_failed:
            return WorkspaceStatus.FAILED
        if has_active:
            return WorkspaceStatus.BUILDING
        if has_stale:
            return WorkspaceStatus.STALE
        return WorkspaceStatus.SUCCESS

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
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
        nodes: dict[str, "DAGNode"] = {}
        for name, nd in data["nodes"].items():
            nodes[name] = DAGNode(
                package=nd["package"],
                version=nd["version"],
                architecture=nd["architecture"],
                status=DAGNodeStatus(nd["status"]),
                commit_sha=nd.get("commit_sha"),
            )
        for name, nd in data["nodes"].items():
            node = nodes[name]
            for dep_name in nd["reverse_dependencies"]:
                if dep_name in nodes:
                    node.reverse_dependencies[dep_name] = nodes[dep_name]
            for dep_name in nd["direct_dependencies"]:
                if dep_name in nodes:
                    node.direct_dependencies[dep_name] = nodes[dep_name]
        return cls(nodes=nodes)

    # ── Private helpers ──────────────────────────────────────────────

    def _calculate_depth(self, package_name: str, memo: dict[str, int]) -> int:
        """Calculate dependency depth with memoization."""
        if package_name in memo:
            return memo[package_name]
        node = self.nodes.get(package_name)
        if node is None or not node.direct_dependencies:
            memo[package_name] = 0
            return 0
        depth = max(
            self._calculate_depth(dep, memo) + 1
            for dep in node.direct_dependencies
        )
        memo[package_name] = depth
        return depth

    def _collect_blocked_dependents(self, failed_package: str) -> list["DAGNode"]:
        """Collect all PENDING transitive dependents of a failed package."""
        return self._traverse_dependents(
            failed_package,
            predicate=lambda node: node.status == DAGNodeStatus.PENDING,
        )

    def _traverse_dependents(
        self,
        start_package: str,
        predicate: Optional[callable] = None,
    ) -> list["DAGNode"]:
        """BFS over reverse_dependencies collecting matching dependents.

        Args:
            start_package: Package name to start traversal from.
            predicate: Optional filter; only nodes satisfying it are collected
                       and further traversed.  When *None*, all reachable
                       dependents are collected.
        """
        collected: dict[str, "DAGNode"] = {}
        visited: set[str] = set()
        queue = [start_package]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            node = self.nodes.get(current)
            if node is None:
                continue
            for dep_name, dep_node in node.reverse_dependencies.items():
                if dep_name in visited:
                    continue
                if predicate is not None and not predicate(dep_node):
                    continue
                collected[dep_name] = dep_node
                queue.append(dep_name)
        return list(collected.values())


class DAGNodeStatus(Enum):
    """Status enumeration for DAG nodes."""

    PENDING = "pending"
    BUILDING = "building"
    SUCCESS = "success"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """True when the node has reached a final state."""
        return self in (DAGNodeStatus.SUCCESS, DAGNodeStatus.FAILED)

    def can_transition_to(self, target: "DAGNodeStatus") -> bool:
        """Check whether transitioning from this status to *target* is valid."""
        return target in _VALID_TRANSITIONS.get(self, set())

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


_VALID_TRANSITIONS: dict[DAGNodeStatus, set[DAGNodeStatus]] = {
    DAGNodeStatus.PENDING: {
        DAGNodeStatus.BUILDING,
        DAGNodeStatus.SUCCESS,
        DAGNodeStatus.FAILED,
    },
    DAGNodeStatus.BUILDING: {
        DAGNodeStatus.SUCCESS,
        DAGNodeStatus.FAILED,
    },
    DAGNodeStatus.SUCCESS: set(),
    DAGNodeStatus.FAILED: set(),
}


@dataclass
class DAGNode:
    """A node in the DAG representing a package and its reverse dependencies."""

    package: str
    version: str
    architecture: str
    reverse_dependencies: dict[str, "DAGNode"] = field(default_factory=dict)
    direct_dependencies: dict[str, "DAGNode"] = field(default_factory=dict)
    project: Optional["Project"] = None
    status: DAGNodeStatus = DAGNodeStatus.PENDING
    buildinfo: Optional["BuildInfo"] = None
    commit_sha: Optional[str] = None
    pipeline_url: Optional[str] = None
    is_stale: bool = False

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
        if not self.buildinfo or not self.buildinfo.binary:
            return False
        return binary_package_name in self.buildinfo.binary

    def set_status(self, new_status: "DAGNodeStatus") -> None:
        self.status = new_status
