# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""
Git-related fixtures and mocks.
"""

from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_git_repo():
    """Create a parametrizable mock of git.Repo."""

    def _create_git_repo(**kwargs):
        remote_url = kwargs.get("remote_url", "git@gitlab.com:your-group/platform-os/pkg/test_sub/example.git")
        branch_name = kwargs.get("branch_name", "main")

        repo = Mock()

        origin = Mock()
        origin.url = remote_url
        repo.remotes = Mock()
        repo.remotes.origin = origin

        branch = Mock()
        branch.name = branch_name
        repo.active_branch = branch

        repo.git = Mock()
        repo.create_remote = Mock()

        return repo

    return _create_git_repo
