# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from lichoscli.commands.workspace import WorkspaceCommand
from lichoscli.core.models import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.core.services import VersionCheckResult
from lichoscli.ui.models import Tree
from tests.mocks import create_mock_args


def test_workspace_graph_passes_stale_packages_to_output_renderer(mock_di_container):
    args = create_mock_args(command="workspace", action="graph", branch="flocken", dump=False, no_wait=False)

    pkg_a = Mock()
    pkg_a.name = "pkg-a"
    pkg_b = Mock()
    pkg_b.name = "pkg-b"

    workspace = Mock()
    workspace.packages = [pkg_a, pkg_b]
    mock_di_container.workspace_service.get_workspace.return_value = workspace

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
    dag = DependencyGraph(nodes={root.package: root, child.package: child})

    mock_di_container.dependency_service.build_dependency_dag.return_value = dag
    mock_di_container.dependency_service.check_all_dependency_versions_from_dag.return_value = [
        VersionCheckResult(
            dependent_package="pkg-b",
            dependent_version="2.0",
            used_version="1.0",
            expected_version="1.1",
            is_correct=False,
            binary_package="lib-a",
            source_package="pkg-a",
        )
    ]

    command = WorkspaceCommand(mock_di_container, args)

    result = command.action_graph()

    assert result == 0
    assert dag.nodes["pkg-b"].is_stale is True
    mock_di_container.user_interface.output.accent.assert_any_call(
        "Dependency Analysis - 2 packages (workspace: flocken)",
    )

    tree_call = mock_di_container.user_interface.output.tree.call_args
    assert tree_call is not None
    tree_arg = tree_call.args[0]
    assert isinstance(tree_arg, Tree)

    root_node = tree_arg.roots[0]
    assert root_node.style == "success"
    assert len(root_node.children) == 1
    stale_child = root_node.children[0]
    assert "pkg-b" in stale_child.label
    assert stale_child.style == "warning"