# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

import pytest

from lichoscli.commands.browse import BrowseCommand
from tests.fixtures.utils import TestConstants
from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    args = create_mock_args()
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.branch = None
    return args


def test_browse_command_initialization(mock_di_container, mock_args):
    command = BrowseCommand(mock_di_container, mock_args)

    assert command.di_container == mock_di_container
    assert command.args == mock_args


@patch("lichoscli.commands.browse.GitRepo.auto_detect")
@patch("lichoscli.commands.browse.subprocess.run")
def test_execute_success(mock_subprocess, mock_auto_detect, mock_di_container, mock_package, mock_args):
    mock_package.web_url = "https://example.com/package"
    mock_di_container.package_service.get_package.return_value = mock_package

    mock_repo_instance = Mock()
    mock_repo_instance.active_branch = TestConstants.DEFAULT_BRANCH
    mock_auto_detect.return_value = mock_repo_instance

    mock_subprocess.return_value.returncode = 0

    command = BrowseCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    mock_subprocess.assert_called_once_with(("xdg-open", "https://example.com/package/tree/main"), check=True)


@patch("lichoscli.commands.browse.GitRepo.auto_detect")
def test_execute_with_branch_specified(mock_auto_detect, mock_di_container, mock_package, mock_args):
    mock_args.branch = "feature-branch"
    mock_package.web_url = "https://example.com/package"
    mock_di_container.package_service.get_package.return_value = mock_package

    with patch("lichoscli.commands.browse.subprocess.run") as mock_subprocess:
        mock_subprocess.return_value.returncode = 0

        command = BrowseCommand(mock_di_container, mock_args)
        result = command.execute()

        assert result == 0
        mock_subprocess.assert_called_once_with(
            ("xdg-open", "https://example.com/package/tree/feature-branch"), check=True
        )
        mock_auto_detect.assert_not_called()


@patch("lichoscli.commands.browse.GitRepo.auto_detect")
def test_execute_package_not_found(mock_auto_detect, mock_di_container, mock_args):
    mock_di_container.package_service.get_package.return_value = None

    mock_repo_instance = Mock()
    mock_repo_instance.active_branch = TestConstants.DEFAULT_BRANCH
    mock_auto_detect.return_value = mock_repo_instance

    command = BrowseCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 1
