# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.core.models.dag import DAGNode, DAGNodeStatus, DependencyGraph


def _node(name, status=DAGNodeStatus.PENDING):
    return DAGNode(package=name, version="1.0", architecture="amd64", status=status)


# ── can_transition_to ────────────────────────────────────────────────


def test_pending_can_transition_to_building():
    assert DAGNodeStatus.PENDING.can_transition_to(DAGNodeStatus.BUILDING) is True


def test_pending_can_transition_to_success():
    assert DAGNodeStatus.PENDING.can_transition_to(DAGNodeStatus.SUCCESS) is True


def test_pending_can_transition_to_failed():
    assert DAGNodeStatus.PENDING.can_transition_to(DAGNodeStatus.FAILED) is True


def test_building_can_transition_to_success():
    assert DAGNodeStatus.BUILDING.can_transition_to(DAGNodeStatus.SUCCESS) is True


def test_building_can_transition_to_failed():
    assert DAGNodeStatus.BUILDING.can_transition_to(DAGNodeStatus.FAILED) is True


def test_building_cannot_transition_to_pending():
    assert DAGNodeStatus.BUILDING.can_transition_to(DAGNodeStatus.PENDING) is False


def test_success_is_terminal_no_transitions():
    for target in DAGNodeStatus:
        assert DAGNodeStatus.SUCCESS.can_transition_to(target) is False


def test_failed_is_terminal_no_transitions():
    for target in DAGNodeStatus:
        assert DAGNodeStatus.FAILED.can_transition_to(target) is False


# ── set_status warnings ─────────────────────────────────────────────


def test_set_status_valid_transition_no_warning(caplog):
    node = _node("pkg-a", status=DAGNodeStatus.PENDING)
    with caplog.at_level(logging.WARNING):
        node.set_status(DAGNodeStatus.BUILDING)
    assert node.status == DAGNodeStatus.BUILDING
    assert caplog.text == ""


# ── mark_* routes through set_status ─────────────────────────────────


def test_mark_building_uses_set_status(caplog):
    dag = DependencyGraph(nodes={"A": _node("A")})
    with caplog.at_level(logging.WARNING):
        dag.mark_building("A")
    assert dag.nodes["A"].status == DAGNodeStatus.BUILDING
    assert caplog.text == ""


def test_mark_succeeded_uses_set_status(caplog):
    dag = DependencyGraph(nodes={"A": _node("A", status=DAGNodeStatus.BUILDING)})
    with caplog.at_level(logging.WARNING):
        dag.mark_succeeded("A")
    assert dag.nodes["A"].status == DAGNodeStatus.SUCCESS
    assert caplog.text == ""


def test_mark_failed_uses_set_status(caplog):
    dag = DependencyGraph(nodes={"A": _node("A", status=DAGNodeStatus.BUILDING)})
    with caplog.at_level(logging.WARNING):
        dag.mark_failed("A")
    assert dag.nodes["A"].status == DAGNodeStatus.FAILED
    assert caplog.text == ""
