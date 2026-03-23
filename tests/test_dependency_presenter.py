# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from lichoscli.commands.workspace import WorkspaceCommand
from lichoscli.core.models import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.core.services import VersionCheckResult
from lichoscli.ui.models import Tree
from lichoscli.ui.presenters.dag import dag_to_tree, version_check_summary
from tests.mocks import create_mock_args


def test_version_check_summary_reports_mismatches():
    results = [
        VersionCheckResult(
            dependent_package="pkg-a",
            dependent_version="1.0",
            used_version="1.0",
            expected_version="2.0",
            is_correct=False,
            binary_package="lib-a",
            source_package="src-a",
        )
    ]
    msg, style = version_check_summary(results)
    assert style == "warning"
    assert "1 version mismatches found" in msg


def test_version_check_summary_all_correct():
    results = [
        VersionCheckResult(
            dependent_package="pkg-a",
            dependent_version="1.0",
            used_version="1.0",
            expected_version="1.0",
            is_correct=True,
            binary_package="lib-a",
            source_package="src-a",
        )
    ]
    msg, style = version_check_summary(results)
    assert style == "success"
    assert "1 dependency version checks passed" in msg


def test_version_check_summary_no_results():
    msg, style = version_check_summary([])
    assert style == "muted"
    assert "All dependency versions match" in msg


def test_workspace_dependency_output_calls_output_tree(mock_di_container):
    command = WorkspaceCommand(
        mock_di_container,
        create_mock_args(command="workspace", action="graph", branch="flocken"),
    )

    root = DAGNode(
        package="pkg-a",
        version="1.0",
        architecture="amd64",
        reverse_dependencies={},
        direct_dependencies={},
        status=DAGNodeStatus.SUCCESS,
    )
    child = DAGNode(
        package="pkg-b",
        version="2.0",
        architecture="amd64",
        reverse_dependencies={},
        direct_dependencies={"pkg-a": root},
        status=DAGNodeStatus.PENDING,
    )
    root.reverse_dependencies[child.package] = child

    other_root = DAGNode(
        package="pkg-c",
        version="3.0",
        architecture="amd64",
        reverse_dependencies={},
        direct_dependencies={},
        status=DAGNodeStatus.FAILED,
    )

    dag = DependencyGraph(
        nodes={
            root.package: root,
            child.package: child,
            other_root.package: other_root,
        }
    )

    mock_di_container.user_interface.output.tree(dag_to_tree(dag))

    call_args = mock_di_container.user_interface.output.tree.call_args
    assert call_args is not None
    tree_arg = call_args.args[0]
    assert isinstance(tree_arg, Tree)
    assert tree_arg.title == "Package Dependency Tree"

    roots = tree_arg.roots
    assert len(roots) == 2

    pkg_a_node = next(n for n in roots if "pkg-a" in n.label)
    pkg_c_node = next(n for n in roots if "pkg-c" in n.label)

    assert pkg_a_node.style == "success"
    assert "v1.0" in pkg_a_node.label
    assert len(pkg_a_node.children) == 1
    assert "pkg-b" in pkg_a_node.children[0].label
    assert pkg_a_node.children[0].style == "muted"

    assert pkg_c_node.style == "error"
    assert "v3.0" in pkg_c_node.label


def test_dag_to_tree_stale_nodes_have_warning_style():
    root = DAGNode(
        package="pkg-a",
        version="1.0",
        architecture="amd64",
        reverse_dependencies={},
        direct_dependencies={},
        status=DAGNodeStatus.SUCCESS,
    )
    child = DAGNode(
        package="pkg-b",
        version="2.0",
        architecture="amd64",
        reverse_dependencies={},
        direct_dependencies={"pkg-a": root},
        status=DAGNodeStatus.SUCCESS,
    )
    root.reverse_dependencies[child.package] = child
    child.is_stale = True

    tree = dag_to_tree(DependencyGraph(nodes={root.package: root, child.package: child}))

    assert len(tree.roots) == 1
    root_node = tree.roots[0]
    assert root_node.style == "success"
    assert len(root_node.children) == 1
    assert root_node.children[0].style == "warning"
