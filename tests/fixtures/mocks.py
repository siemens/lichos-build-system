# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""
Generic mock fixtures for common testing patterns.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    """Fixture that provides basic mock arguments."""
    return create_mock_args()


@pytest.fixture
def mock_os_exists():
    """Mock os.path.exists."""
    with patch("os.path.exists") as m:
        yield m


@pytest.fixture
def mock_file():
    """Mock file operations."""
    with patch("builtins.open", new_callable=mock_open) as m:
        yield m


@pytest.fixture
def mock_yaml():
    """Mock YAML loading."""
    with patch("yaml.safe_load") as m:
        yield m


@pytest.fixture
def mock_gitlab_module():
    """Mock the gitlab module."""
    with patch("gitlab.Gitlab") as m:
        yield m


@pytest.fixture
def magic_mock():
    """Provide a MagicMock instance."""
    return MagicMock()
