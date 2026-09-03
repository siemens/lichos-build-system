# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from lichoscli.commands.workspace import WorkspaceCommand
from lichoscli.core.models import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.core.services import VersionCheckResult
from lichoscli.ui.models import Tree
from tests.mocks import create_mock_args


def _merge_request(iid, approved=True, merge_result=True):
    mr = Mock()
    mr.iid = str(iid)
    mr.title = f"MR {iid}"
    mr.is_approved.return_value = approved
    mr.merge.return_value = merge_result
    return mr


def _package(name, merge_requests):
    package = Mock()
    package.name = name
    package.default_branch = "main"
    package.merge_requests.list.return_value = merge_requests
    package.get_commits.return_value = []
    package.compare_url.side_effect = (
        lambda from_ref, to_ref: f"https://gitlab.example/{name}/{from_ref}...{to_ref}"
    )
    return package


def _dependency_dag(*package_names):
    nodes = {
        name: DAGNode(
            package=name,
            version="1.0",
            architecture="amd64",
            status=DAGNodeStatus.SUCCESS,
        )
        for name in package_names
    }
    for dependency_name, dependent_name in zip(package_names, package_names[1:]):
        nodes[dependent_name].add_dependency(nodes[dependency_name])
        nodes[dependency_name].add_dependent(nodes[dependent_name])
    return DependencyGraph(nodes=nodes)


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


def test_workspace_merge_aborts_before_merging_when_any_mr_is_unapproved(mock_di_container):
    args = create_mock_args(command="workspace", action="merge", branch="flocken")
    approved_mr = _merge_request(1, approved=True)
    unapproved_mr = _merge_request(2, approved=False)
    packages = [
        _package("dependency", [approved_mr]),
        _package("dependent", [unapproved_mr]),
    ]
    workspace = Mock(packages=packages)
    mock_di_container.workspace_service.get_workspace.return_value = workspace

    result = WorkspaceCommand(mock_di_container, args).action_merge()

    assert result == 1
    approved_mr.merge.assert_not_called()
    unapproved_mr.merge.assert_not_called()
    mock_di_container.dependency_service.build_dependency_dag.assert_not_called()
    mock_di_container.user_interface.output.error.assert_any_call(
        "Workspace merge aborted: all open merge requests must be approved",
    )


def test_workspace_merge_aborts_for_changed_branch_without_open_mr(mock_di_container):
    args = create_mock_args(command="workspace", action="merge", branch="flocken")
    reviewed_mr = _merge_request(1)
    reviewed_package = _package("reviewed", [reviewed_mr])
    unreviewed_package = _package("unreviewed", [])
    unreviewed_package.get_commits.side_effect = [
        [{"id": "workspace-change"}],
        [],
    ]
    workspace = Mock(packages=[reviewed_package, unreviewed_package])
    mock_di_container.workspace_service.get_workspace.return_value = workspace

    result = WorkspaceCommand(mock_di_container, args).action_merge()

    assert result == 1
    reviewed_mr.is_approved.assert_not_called()
    reviewed_mr.merge.assert_not_called()
    mock_di_container.dependency_service.build_dependency_dag.assert_not_called()
    unreviewed_package.get_commits.assert_any_call("main", "flocken")
    unreviewed_package.get_commits.assert_any_call("flocken", "main")
    mock_di_container.user_interface.output.error.assert_any_call(
        "Workspace merge aborted: the workspace has not been fully reviewed",
    )
    mock_di_container.user_interface.output.error.assert_any_call(
        "  - unreviewed (ahead): "
        "https://gitlab.example/unreviewed/main...flocken",
    )
    mock_di_container.user_interface.output.print.assert_any_call(
        "Review all changes with: "
        "lichoscli --branch flocken workspace changes",
    )


def test_workspace_merge_allows_stale_branch_without_open_mr(mock_di_container):
    args = create_mock_args(command="workspace", action="merge", branch="flocken")
    stale_package = _package("stale", [])
    stale_package.get_commits.side_effect = [
        [],
        [{"id": "default-branch-change"}],
    ]
    workspace = Mock(packages=[stale_package])
    mock_di_container.workspace_service.get_workspace.return_value = workspace

    result = WorkspaceCommand(mock_di_container, args).action_merge()

    assert result == 0
    mock_di_container.dependency_service.build_dependency_dag.assert_not_called()
    mock_di_container.user_interface.output.print.assert_any_call(
        "Total merge requests found: 0",
    )


def test_workspace_merge_uses_dependency_order_not_workspace_order(mock_di_container):
    args = create_mock_args(command="workspace", action="merge", branch="flocken")
    merge_order = []
    root_mr = _merge_request(1)
    middle_mr = _merge_request(2)
    leaf_mr = _merge_request(3)
    root_mr.merge.side_effect = lambda: merge_order.append("root") or True
    middle_mr.merge.side_effect = lambda: merge_order.append("middle") or True
    leaf_mr.merge.side_effect = lambda: merge_order.append("leaf") or True

    packages = [
        _package("leaf", [leaf_mr]),
        _package("root", [root_mr]),
        _package("middle", [middle_mr]),
    ]
    workspace = Mock(packages=packages)
    mock_di_container.workspace_service.get_workspace.return_value = workspace
    mock_di_container.dependency_service.build_dependency_dag.return_value = (
        _dependency_dag("root", "middle", "leaf")
    )

    result = WorkspaceCommand(mock_di_container, args).action_merge()

    assert result == 0
    assert merge_order == ["root", "middle", "leaf"]
    mock_di_container.dependency_service.build_dependency_dag.assert_called_once_with(
        packages,
        "flocken",
        wait_for_completion=False,
    )


def test_workspace_merge_stops_before_dependents_after_failure(mock_di_container):
    args = create_mock_args(command="workspace", action="merge", branch="flocken")
    dependency_mr = _merge_request(1, merge_result=False)
    dependent_mr = _merge_request(2)
    packages = [
        _package("dependency", [dependency_mr]),
        _package("dependent", [dependent_mr]),
    ]
    workspace = Mock(packages=packages)
    mock_di_container.workspace_service.get_workspace.return_value = workspace
    mock_di_container.dependency_service.build_dependency_dag.return_value = (
        _dependency_dag("dependency", "dependent")
    )

    result = WorkspaceCommand(mock_di_container, args).action_merge()

    assert result == 1
    dependency_mr.merge.assert_called_once_with()
    dependent_mr.merge.assert_not_called()


def test_workspace_merge_aborts_when_dependency_graph_is_incomplete(mock_di_container):
    args = create_mock_args(command="workspace", action="merge", branch="flocken")
    merge_request = _merge_request(1)
    packages = [
        _package("with-mr", [merge_request]),
        _package("missing-from-graph", []),
    ]
    workspace = Mock(packages=packages)
    mock_di_container.workspace_service.get_workspace.return_value = workspace
    mock_di_container.dependency_service.build_dependency_dag.return_value = (
        _dependency_dag("with-mr")
    )

    result = WorkspaceCommand(mock_di_container, args).action_merge()

    assert result == 1
    merge_request.merge.assert_not_called()
    mock_di_container.user_interface.output.error.assert_any_call(
        "Workspace merge aborted: could not determine dependency order for "
        "missing-from-graph",
    )
