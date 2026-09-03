# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from lichoscli.providers.gitlab.models.workspace import GitLabWorkspace


def _package(name, protected):
    pkg = Mock()
    pkg.name = name
    pkg.is_branch_protected.return_value = protected
    return pkg


def test_protected_when_any_package_branch_is_protected():
    workspace = GitLabWorkspace(
        name="release/1.0",
        packages=[_package("a", False), _package("b", True)],
    )

    assert workspace.is_protected is True


def test_not_protected_when_no_package_branch_is_protected():
    workspace = GitLabWorkspace(
        name="feature/x",
        packages=[_package("a", False), _package("b", False)],
    )

    assert workspace.is_protected is False


def test_not_protected_without_packages():
    assert GitLabWorkspace(name="feature/x", packages=[]).is_protected is False
