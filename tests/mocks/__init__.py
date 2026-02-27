# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""
Test mocks package for lichoscli.

This package contains mock implementations for testing GitLab API interactions
and utilities for creating mock objects across different test scenarios.
"""

from .args import MockArgsBuilder, create_mock_args
from .gitlab_client import MockGitLab
from .gitlab_group import MockGitLabGroup
from .gitlab_project import MockGitLabProject

__all__ = [
    "create_mock_args",
    "MockArgsBuilder",
    "MockGitLab",
    "MockGitLabGroup",
    "MockGitLabProject",
]
