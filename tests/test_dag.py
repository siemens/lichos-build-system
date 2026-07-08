# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from lichoscli.core.models import DAGNode, DAGNodeStatus, DependencyGraph, WorkspaceStatus
from lichoscli.core.services import VersionCheckResult


# ── helpers ──────────────────────────────────────────────────────────


def _node(name, status=DAGNodeStatus.PENDING):
    return DAGNode(package=name, version="1.0", architecture="amd64", status=status)


def _diamond_dag():
    """
    Build a diamond-shaped DAG:  A → B, A → C, B → D, C → D

        A          depth 0
       / \\
      B   C        depth 1
       \\ /
        D          depth 2
    """
    a = _node("A")
    b = _node("B")
    c = _node("C")
    d = _node("D")

    b.add_dependency(a)
    a.add_dependent(b)
    c.add_dependency(a)
    a.add_dependent(c)
    d.add_dependency(b)
    b.add_dependent(d)
    d.add_dependency(c)
    c.add_dependent(d)

    return DependencyGraph(nodes={"A": a, "B": b, "C": c, "D": d})


# ── scheduling primitives ───────────────────────────────────────────


def test_get_ready_nodes_returns_roots_when_all_pending():
    dag = _diamond_dag()
    ready = dag.get_ready_nodes()
    assert [n.package for n in ready] == ["A"]


def test_get_ready_nodes_after_root_succeeds():
    dag = _diamond_dag()
    dag.mark_building("A")
    dag.mark_succeeded("A")

    ready = dag.get_ready_nodes()
    names = sorted(n.package for n in ready)
    assert names == ["B", "C"]


def test_get_ready_nodes_excludes_building_and_succeeded():
    dag = _diamond_dag()
    dag.mark_building("A")
    assert dag.get_ready_nodes() == []


def test_mark_succeeded_returns_newly_ready():
    dag = _diamond_dag()
    dag.mark_building("A")
    newly_ready = dag.mark_succeeded("A")
    names = sorted(n.package for n in newly_ready)
    assert names == ["B", "C"]


def test_mark_succeeded_does_not_return_node_with_pending_deps():
    dag = _diamond_dag()
    dag.mark_building("A")
    dag.mark_succeeded("A")
    dag.mark_building("B")

    # B succeeds but D still depends on C (PENDING) → D not ready
    newly_ready = dag.mark_succeeded("B")
    assert newly_ready == []


def test_mark_succeeded_unlocks_d_when_both_deps_done():
    dag = _diamond_dag()
    dag.mark_building("A")
    dag.mark_succeeded("A")
    dag.mark_building("B")
    dag.mark_building("C")
    dag.mark_succeeded("B")
    newly_ready = dag.mark_succeeded("C")
    assert [n.package for n in newly_ready] == ["D"]


def test_mark_failed_returns_blocked_dependents():
    dag = _diamond_dag()
    dag.mark_building("A")
    blocked = dag.mark_failed("A")
    blocked_names = sorted(n.package for n in blocked)
    assert blocked_names == ["B", "C", "D"]


def test_mark_failed_partial_blocks_only_affected_branch():
    """When B fails after A succeeds, only D is blocked (C is unaffected)."""
    dag = _diamond_dag()
    dag.mark_building("A")
    dag.mark_succeeded("A")
    dag.mark_building("B")
    dag.mark_building("C")

    blocked = dag.mark_failed("B")
    blocked_names = sorted(n.package for n in blocked)
    # D depends on both B and C; B failed → D is blocked
    assert blocked_names == ["D"]


def test_is_complete_false_when_pending():
    dag = _diamond_dag()
    assert dag.is_complete() is False


def test_is_complete_true_when_all_terminal():
    dag = _diamond_dag()
    for name in dag.nodes:
        dag.nodes[name].set_status(DAGNodeStatus.SUCCESS)
    assert dag.is_complete() is True


def test_is_complete_true_with_mix_of_success_and_failed():
    dag = _diamond_dag()
    dag.nodes["A"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["B"].set_status(DAGNodeStatus.FAILED)
    dag.nodes["C"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["D"].set_status(DAGNodeStatus.FAILED)
    assert dag.is_complete() is True


def test_get_blocked_nodes():
    dag = _diamond_dag()
    dag.mark_building("A")
    dag.mark_failed("A")

    blocked = dag.get_blocked_nodes()
    blocked_names = sorted(n.package for n in blocked)
    assert blocked_names == ["B", "C", "D"]


def test_get_roots():
    dag = _diamond_dag()
    roots = dag.get_roots()
    assert [n.package for n in roots] == ["A"]


def test_dag_node_status_is_terminal():
    assert DAGNodeStatus.PENDING.is_terminal is False
    assert DAGNodeStatus.BUILDING.is_terminal is False
    assert DAGNodeStatus.SUCCESS.is_terminal is True
    assert DAGNodeStatus.FAILED.is_terminal is True


# ── graph analysis ──────────────────────────────────────────────────


def test_group_by_depth():
    dag = _diamond_dag()
    levels = dag.group_by_depth()
    assert sorted(levels.keys()) == [0, 1, 2]
    assert [n.package for n in levels[0]] == ["A"]
    assert sorted(n.package for n in levels[1]) == ["B", "C"]
    assert [n.package for n in levels[2]] == ["D"]


def test_group_by_depth_with_subset():
    dag = _diamond_dag()
    subset = [dag.nodes["B"], dag.nodes["D"]]
    levels = dag.group_by_depth(subset)
    assert sorted(levels.keys()) == [1, 2]


def test_get_depth():
    dag = _diamond_dag()
    assert dag.get_depth("A") == 0
    assert dag.get_depth("B") == 1
    assert dag.get_depth("C") == 1
    assert dag.get_depth("D") == 2


def test_get_depth_with_shared_memo_populates_across_calls():
    dag = _diamond_dag()
    memo: dict[str, int] = {}
    assert dag.get_depth("A", memo) == 0
    assert dag.get_depth("B", memo) == 1
    assert dag.get_depth("C", memo) == 1
    assert dag.get_depth("D", memo) == 2
    assert memo == {"A": 0, "B": 1, "C": 1, "D": 2}


def test_get_depth_omitted_memo_uses_fresh_dict():
    dag = _diamond_dag()
    dag.get_depth("A")
    dag.get_depth("B")
    assert dag.get_depth("A") == 0
    assert dag.get_depth("B") == 1


def test_get_transitive_dependents():
    dag = _diamond_dag()
    deps = dag.get_transitive_dependents("A")
    names = sorted(n.package for n in deps)
    assert names == ["B", "C", "D"]


def test_get_transitive_dependents_leaf():
    dag = _diamond_dag()
    assert dag.get_transitive_dependents("D") == []


def test_remove_node_cleans_edges():
    dag = _diamond_dag()
    dag.remove_node("B")
    assert "B" not in dag.nodes
    assert "B" not in dag.nodes["A"].reverse_dependencies
    assert "B" not in dag.nodes["D"].direct_dependencies


def test_dag_node_field_defaults():
    """DAGNode reverse/direct_dependencies default to empty dicts."""
    node = DAGNode(package="test", version="1.0", architecture="amd64")
    assert node.reverse_dependencies == {}
    assert node.direct_dependencies == {}


# ── serialization round-trip ────────────────────────────────────────


def test_to_dict_from_dict_roundtrip():
    dag = _diamond_dag()
    dag.nodes["A"].set_status(DAGNodeStatus.SUCCESS)

    restored = DependencyGraph.from_dict(dag.to_dict())

    assert set(restored.nodes.keys()) == {"A", "B", "C", "D"}
    assert restored.nodes["A"].status == DAGNodeStatus.SUCCESS
    assert "B" in restored.nodes["A"].reverse_dependencies
    assert "A" in restored.nodes["B"].direct_dependencies


# ── scheduling full loop simulation ─────────────────────────────────


def test_full_scheduling_loop():
    """Simulate a complete build run through the DAG scheduling API."""
    dag = _diamond_dag()

    # Round 1: only A is ready
    ready = dag.get_ready_nodes()
    assert [n.package for n in ready] == ["A"]
    dag.mark_building("A")

    # A succeeds → B, C become ready
    newly_ready = dag.mark_succeeded("A")
    assert sorted(n.package for n in newly_ready) == ["B", "C"]

    # Round 2: B and C build in parallel
    dag.mark_building("B")
    dag.mark_building("C")

    dag.mark_succeeded("B")
    newly_ready_c = dag.mark_succeeded("C")
    assert [n.package for n in newly_ready_c] == ["D"]

    # Round 3: D
    dag.mark_building("D")
    dag.mark_succeeded("D")

    assert dag.is_complete() is True
    assert len(dag.get_blocked_nodes()) == 0


def test_scheduling_with_failure():
    """A root failure blocks the entire graph."""
    dag = _diamond_dag()

    dag.mark_building("A")
    blocked = dag.mark_failed("A")
    assert sorted(n.package for n in blocked) == ["B", "C", "D"]

    # No ready nodes, no building nodes → done
    assert dag.get_ready_nodes() == []
    assert dag.get_nodes_by_status(DAGNodeStatus.BUILDING) == []


def test_scheduling_partial_failure():
    """When B fails, only D is blocked; C continues independently."""
    dag = _diamond_dag()

    dag.mark_building("A")
    dag.mark_succeeded("A")

    dag.mark_building("B")
    dag.mark_building("C")

    dag.mark_failed("B")
    dag.mark_succeeded("C")

    # D depends on both B and C; B failed → D not ready
    assert dag.get_ready_nodes() == []
    blocked = dag.get_blocked_nodes()
    assert [n.package for n in blocked] == ["D"]


# ── staleness (existing test, kept) ─────────────────────────────────


def test_dependency_graph_apply_version_check_results_marks_stale_nodes():
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

    stale_packages = dag.apply_version_check_results(
        [
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
    )

    assert stale_packages == {"pkg-b"}
    assert dag.get_stale_packages() == {"pkg-b"}
    assert dag.nodes["pkg-a"].is_stale is False
    assert dag.nodes["pkg-b"].is_stale is True


# ── compute_workspace_status ────────────────────────────────────────


def test_compute_workspace_status_all_success():
    dag = _diamond_dag()
    for node in dag.nodes.values():
        node.set_status(DAGNodeStatus.SUCCESS)
    assert dag.compute_workspace_status() == WorkspaceStatus.SUCCESS


def test_compute_workspace_status_any_failed():
    dag = _diamond_dag()
    dag.nodes["A"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["B"].set_status(DAGNodeStatus.FAILED)
    dag.nodes["C"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["D"].set_status(DAGNodeStatus.SUCCESS)
    assert dag.compute_workspace_status() == WorkspaceStatus.FAILED


def test_compute_workspace_status_building():
    dag = _diamond_dag()
    dag.nodes["A"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["B"].set_status(DAGNodeStatus.BUILDING)
    dag.nodes["C"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["D"].set_status(DAGNodeStatus.SUCCESS)
    assert dag.compute_workspace_status() == WorkspaceStatus.BUILDING


def test_compute_workspace_status_pending_means_building():
    dag = _diamond_dag()
    for node in dag.nodes.values():
        node.set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["D"].status = DAGNodeStatus.PENDING
    assert dag.compute_workspace_status() == WorkspaceStatus.BUILDING


def test_compute_workspace_status_stale():
    dag = _diamond_dag()
    for node in dag.nodes.values():
        node.set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["B"].is_stale = True
    assert dag.compute_workspace_status() == WorkspaceStatus.STALE


def test_compute_workspace_status_failed_takes_priority_over_building():
    dag = _diamond_dag()
    dag.nodes["A"].set_status(DAGNodeStatus.FAILED)
    dag.nodes["B"].set_status(DAGNodeStatus.BUILDING)
    dag.nodes["C"].set_status(DAGNodeStatus.SUCCESS)
    dag.nodes["D"].set_status(DAGNodeStatus.SUCCESS)
    assert dag.compute_workspace_status() == WorkspaceStatus.FAILED


def test_mark_succeeded_clears_is_stale_flag():
    """A node built after being marked stale must not leave workspace in STALE state."""
    dag = _diamond_dag()
    for node in dag.nodes.values():
        node.set_status(DAGNodeStatus.PENDING)
        node.is_stale = True
    dag.mark_building("A")
    dag.mark_succeeded("A")
    assert not dag.nodes["A"].is_stale


def test_compute_workspace_status_success_after_stale_nodes_rebuilt():
    """Workspace status must be SUCCESS when all formerly-stale nodes have been rebuilt."""
    dag = _diamond_dag()
    for node in dag.nodes.values():
        node.set_status(DAGNodeStatus.PENDING)
        node.is_stale = True
    for name in list(dag.nodes.keys()):
        dag.mark_building(name)
        dag.mark_succeeded(name)
    assert dag.compute_workspace_status() == WorkspaceStatus.SUCCESS