# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Presenter helpers that convert DAG domain objects to generic UI models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from lichoscli.ui.models import CellStyle, Tree, TreeNode
from lichoscli.core.models.dag import DAGNodeStatus

if TYPE_CHECKING:
    from lichoscli.core.models.dag import DAGNode, DependencyGraph


def dag_node_style(node: "DAGNode") -> Optional[CellStyle]:
    """Map a DAGNode to a semantic CellStyle based on its status and staleness."""

    if node.status == DAGNodeStatus.FAILED:
        return "error"
    if node.status == DAGNodeStatus.BUILDING:
        return "info"
    if node.is_stale:
        return "warning"
    if node.status == DAGNodeStatus.SUCCESS:
        return "success"
    return "muted"


def dag_node_label(node: "DAGNode") -> str:
    """Build a display label for a DAGNode including its version when known."""
    label = node.package
    if node.version and node.version != "unknown":
        label = "{0} v{1}".format(node.package, node.version)
    return label


def _build_tree_node(dag_node: "DAGNode", visited: frozenset) -> TreeNode:
    """Recursively build a TreeNode from a DAGNode, guarding against cycles."""
    label = dag_node_label(dag_node)
    if dag_node.package in visited:
        return TreeNode(label="{0} (circular)".format(dag_node.package), style="error")

    style = dag_node_style(dag_node)
    next_visited = visited | frozenset([dag_node.package])
    children = [
        _build_tree_node(child, next_visited)
        for child in sorted(dag_node.reverse_dependencies.values(), key=lambda n: n.package)
    ]
    return TreeNode(label=label, style=style, children=children)


def dag_to_tree(dag: "DependencyGraph", title: str = "Package Dependency Tree") -> Tree:
    """Convert a DependencyGraph into a renderable Tree model.

    Root nodes are packages with no direct dependencies.  When none exist
    (fully circular graph), all nodes are used as roots as a fallback.
    """
    tree = Tree(title=title)

    if not dag.nodes:
        return tree

    root_dag_nodes = sorted(
        [node for node in dag.nodes.values() if not node.direct_dependencies],
        key=lambda node: node.package,
    )

    if not root_dag_nodes:
        root_dag_nodes = sorted(dag.nodes.values(), key=lambda node: node.package)

    for dag_node in root_dag_nodes:
        tree.add_root(_build_tree_node(dag_node, frozenset()))

    return tree


def version_check_summary(results: list) -> tuple[str, str]:
    """Return a (message, CellStyle) pair summarising dependency version check results.

    Args:
        results: List of VersionCheckResult objects.

    Returns:
        A tuple of (message text, CellStyle) suitable for passing to an OutputWriter
        method such as output.success() or output.warning().
    """
    if not results:
        return (
            "All dependency versions match the expected values. No mismatches found.",
            "muted",
        )

    correct_count = sum(1 for result in results if result.is_correct)
    incorrect_count = len(results) - correct_count

    if incorrect_count == 0:
        return ("All {0} dependency version checks passed.".format(correct_count), "success")

    return (
        "{0} version mismatches found, {1} checks correct.".format(incorrect_count, correct_count),
        "warning",
    )
