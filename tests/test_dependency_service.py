# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Tests for GitLabDependencyService.get_dag_changed_packages."""

import unittest
from unittest.mock import Mock

from lichoscli.core.models.dag import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.providers.gitlab.services.dependency_service import GitLabDependencyService


def _make_node(package: str, commit_sha: str | None, project=None, version: str = "1.0") -> DAGNode:
    """Helper to create a minimal DAGNode."""
    return DAGNode(
        package=package,
        version=version,
        architecture="amd64",
        reverse_dependencies={},
        direct_dependencies={},
        status=DAGNodeStatus.PENDING,
        commit_sha=commit_sha,
        project=project or Mock(path_with_namespace="group/{}".format(package)),
    )


def _make_dag(nodes: list[DAGNode]) -> DependencyGraph:
    dag = DependencyGraph(nodes={})
    for node in nodes:
        dag.add_node(node)
    return dag


class TestGetDagChangedPackages(unittest.TestCase):
    def setUp(self):
        buildinfo_service = Mock()
        self.service = GitLabDependencyService(buildinfo_service)

    def test_unchanged_package_is_not_reported(self):
        """Packages with the same commit SHA in old and new DAG must not appear in the result."""
        node_old = _make_node("pkg-a", commit_sha="abc123")
        node_new = _make_node("pkg-a", commit_sha="abc123")

        old_dag = _make_dag([node_old])
        new_dag = _make_dag([node_new])

        result = self.service.get_dag_changed_packages(old_dag, new_dag)

        self.assertNotIn("pkg-a", result)

    def test_changed_package_is_reported(self):
        """Packages whose commit SHA changed must appear in the result."""
        node_old = _make_node("pkg-b", commit_sha="aaaaaa")
        node_new = _make_node("pkg-b", commit_sha="bbbbbb")

        old_dag = _make_dag([node_old])
        new_dag = _make_dag([node_new])

        result = self.service.get_dag_changed_packages(old_dag, new_dag)

        self.assertIn("pkg-b", result)
        project, old_commit, new_commit = result["pkg-b"]
        self.assertEqual(old_commit, "aaaaaa")
        self.assertEqual(new_commit, "bbbbbb")

    def test_new_package_only_in_new_dag_is_reported(self):
        """Packages that exist only in the new DAG (newly added) must be included."""
        node_new = _make_node("pkg-new", commit_sha="cccccc")

        old_dag = _make_dag([])
        new_dag = _make_dag([node_new])

        result = self.service.get_dag_changed_packages(old_dag, new_dag)

        self.assertIn("pkg-new", result)
        project, old_commit, new_commit = result["pkg-new"]
        self.assertIsNone(old_commit)
        self.assertEqual(new_commit, "cccccc")

    def test_mixed_packages_only_changed_ones_reported(self):
        """Only packages with differing commit SHAs (or new) are in the result."""
        unchanged = _make_node("unchanged", commit_sha="same")
        changed_old = _make_node("changed", commit_sha="old-sha")
        changed_new = _make_node("changed", commit_sha="new-sha")
        new_pkg = _make_node("brand-new", commit_sha="fresh")

        old_dag = _make_dag([unchanged, changed_old])
        new_dag = _make_dag([
            _make_node("unchanged", commit_sha="same"),
            changed_new,
            new_pkg,
        ])

        result = self.service.get_dag_changed_packages(old_dag, new_dag)

        self.assertNotIn("unchanged", result, "Unchanged package should not be reported")
        self.assertIn("changed", result, "Changed package should be reported")
        self.assertIn("brand-new", result, "New package should be reported")
        self.assertEqual(len(result), 2)

    def test_package_removed_from_new_dag_is_not_reported(self):
        """Packages that exist only in the old DAG (removed) must not appear."""
        node_old = _make_node("removed-pkg", commit_sha="abc")

        old_dag = _make_dag([node_old])
        new_dag = _make_dag([])

        result = self.service.get_dag_changed_packages(old_dag, new_dag)

        self.assertNotIn("removed-pkg", result)

    def test_commit_sha_both_none_is_not_reported(self):
        """Packages with commit_sha=None in both states are unchanged and should not be reported."""
        node_old = _make_node("pkg-null", commit_sha=None)
        node_new = _make_node("pkg-null", commit_sha=None)

        old_dag = _make_dag([node_old])
        new_dag = _make_dag([node_new])

        result = self.service.get_dag_changed_packages(old_dag, new_dag)

        self.assertNotIn("pkg-null", result)


if __name__ == "__main__":
    unittest.main()


class TestHasDagStateChanged(unittest.TestCase):
    def setUp(self):
        buildinfo_service = Mock()
        self.service = GitLabDependencyService(buildinfo_service)

    def test_unchanged_dag_returns_false(self):
        """Identical DAGs should report no changes."""
        old_dag = _make_dag([_make_node("pkg-a", commit_sha="abc", version="1.0")])
        new_dag = _make_dag([_make_node("pkg-a", commit_sha="abc", version="1.0")])

        self.assertFalse(self.service.has_dag_state_changed(old_dag, new_dag))

    def test_commit_change_returns_true(self):
        """A changed commit SHA should be detected."""
        old_dag = _make_dag([_make_node("pkg-a", commit_sha="abc", version="1.0")])
        new_dag = _make_dag([_make_node("pkg-a", commit_sha="def", version="1.0")])

        self.assertTrue(self.service.has_dag_state_changed(old_dag, new_dag))

    def test_version_change_same_commit_returns_true(self):
        """A new pipeline on the same commit produces a new version and must be detected."""
        old_dag = _make_dag([_make_node("pkg-a", commit_sha="abc", version="1.0+lichos37")])
        new_dag = _make_dag([_make_node("pkg-a", commit_sha="abc", version="1.0+lichos38")])

        self.assertTrue(self.service.has_dag_state_changed(old_dag, new_dag))

    def test_package_count_change_returns_true(self):
        """Adding a package should be detected."""
        old_dag = _make_dag([_make_node("pkg-a", commit_sha="abc")])
        new_dag = _make_dag([
            _make_node("pkg-a", commit_sha="abc"),
            _make_node("pkg-b", commit_sha="def"),
        ])

        self.assertTrue(self.service.has_dag_state_changed(old_dag, new_dag))

    def test_status_change_alone_returns_false(self):
        """A failed build with unchanged inputs must not trigger another rebuild."""
        old_node = _make_node("pkg-a", commit_sha="abc")
        old_node.status = DAGNodeStatus.SUCCESS
        new_node = _make_node("pkg-a", commit_sha="abc")
        new_node.status = DAGNodeStatus.FAILED

        old_dag = _make_dag([old_node])
        new_dag = _make_dag([new_node])

        self.assertFalse(self.service.has_dag_state_changed(old_dag, new_dag))
