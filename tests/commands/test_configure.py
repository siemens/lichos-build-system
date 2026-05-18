# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import pytest

from lichoscli.commands.configure import ConfigureCommand
from lichoscli.core.exceptions import ProjectFetchingError
from tests.fixtures.utils import TestConstants
from tests.mocks import create_mock_args


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_parent(mock_gitlab_project):
    pkg = mock_gitlab_project(id=999, name="parent-package")
    return pkg


@pytest.fixture
def fork_set_args():
    args = create_mock_args()
    args.configure_action = "fork"
    args.fork_action = "set"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.parent = "parent-package"
    return args


@pytest.fixture
def fork_unset_args():
    args = create_mock_args()
    args.configure_action = "fork"
    args.fork_action = "unset"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    return args


@pytest.fixture
def fp_enable_args():
    args = create_mock_args()
    args.configure_action = "forcepush"
    args.forcepush_action = "enable"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.branch = TestConstants.DEFAULT_BRANCH
    return args


@pytest.fixture
def fp_disable_args():
    args = create_mock_args()
    args.configure_action = "forcepush"
    args.forcepush_action = "disable"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.branch = TestConstants.DEFAULT_BRANCH
    return args


# ---------------------------------------------------------------------------
# fork set
# ---------------------------------------------------------------------------


def test_fork_set_success(mock_di_container, mock_package, mock_parent, fork_set_args):
    mock_di_container.package_service.get_package.side_effect = [mock_package, mock_parent]

    cmd = ConfigureCommand(mock_di_container, fork_set_args)
    result = cmd.execute()

    assert result == 0
    mock_package.create_fork_relation.assert_called_once_with(mock_parent.id)


def test_fork_set_package_not_found(mock_di_container, fork_set_args):
    mock_di_container.package_service.get_package.return_value = None

    cmd = ConfigureCommand(mock_di_container, fork_set_args)
    result = cmd.execute()

    assert result == 1


def test_fork_set_parent_not_found(mock_di_container, mock_package, fork_set_args):
    mock_di_container.package_service.get_package.side_effect = [mock_package, None]

    cmd = ConfigureCommand(mock_di_container, fork_set_args)
    result = cmd.execute()

    assert result == 1
    mock_package.create_fork_relation.assert_not_called()


def test_fork_set_api_error(mock_di_container, mock_package, mock_parent, fork_set_args):
    mock_di_container.package_service.get_package.side_effect = [mock_package, mock_parent]
    mock_package.create_fork_relation.side_effect = ProjectFetchingError("API error")

    cmd = ConfigureCommand(mock_di_container, fork_set_args)
    result = cmd.execute()

    assert result == 1

@pytest.fixture
def fork_set_url_args():
    args = create_mock_args()
    args.configure_action = "fork"
    args.fork_action = "set"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.parent = "https://gitlab.example.com/your-group/platform-os/pkg/image-qemu"
    return args


def test_fork_set_url_parent_success(mock_di_container, mock_package, mock_parent, fork_set_url_args):
    mock_di_container.package_service.get_package.return_value = mock_package
    mock_di_container.package_service.get_project_by_url.return_value = mock_parent

    cmd = ConfigureCommand(mock_di_container, fork_set_url_args)
    result = cmd.execute()

    assert result == 0
    mock_di_container.package_service.get_project_by_url.assert_called_once_with(
        "https://gitlab.example.com/your-group/platform-os/pkg/image-qemu"
    )
    mock_di_container.package_service.get_package.assert_called_once_with(TestConstants.DEFAULT_PROJECT_NAME)
    mock_package.create_fork_relation.assert_called_once_with(mock_parent.id)


def test_fork_set_url_parent_not_found(mock_di_container, mock_package, fork_set_url_args):
    mock_di_container.package_service.get_package.return_value = mock_package
    mock_di_container.package_service.get_project_by_url.return_value = None

    cmd = ConfigureCommand(mock_di_container, fork_set_url_args)
    result = cmd.execute()

    assert result == 1
    mock_package.create_fork_relation.assert_not_called()


# ---------------------------------------------------------------------------
# fork unset
# ---------------------------------------------------------------------------


def test_fork_unset_success(mock_di_container, mock_package, fork_unset_args):
    mock_package.is_fork = True
    mock_di_container.package_service.get_package.return_value = mock_package

    cmd = ConfigureCommand(mock_di_container, fork_unset_args)
    result = cmd.execute()

    assert result == 0
    mock_package.delete_fork_relation.assert_called_once()


def test_fork_unset_not_a_fork(mock_di_container, mock_package, fork_unset_args):
    mock_package.is_fork = False
    mock_di_container.package_service.get_package.return_value = mock_package

    cmd = ConfigureCommand(mock_di_container, fork_unset_args)
    result = cmd.execute()

    # Should still proceed and return 0
    assert result == 0
    mock_package.delete_fork_relation.assert_called_once()


def test_fork_unset_package_not_found(mock_di_container, fork_unset_args):
    mock_di_container.package_service.get_package.return_value = None

    cmd = ConfigureCommand(mock_di_container, fork_unset_args)
    result = cmd.execute()

    assert result == 1


def test_fork_unset_api_error(mock_di_container, mock_package, fork_unset_args):
    mock_package.is_fork = True
    mock_di_container.package_service.get_package.return_value = mock_package
    mock_package.delete_fork_relation.side_effect = ProjectFetchingError("API error")

    cmd = ConfigureCommand(mock_di_container, fork_unset_args)
    result = cmd.execute()

    assert result == 1


# ---------------------------------------------------------------------------
# forcepush enable / disable
# ---------------------------------------------------------------------------


def test_forcepush_enable_success(mock_di_container, mock_package, fp_enable_args):
    mock_package.set_force_push.return_value = True
    mock_di_container.package_service.get_package.return_value = mock_package

    cmd = ConfigureCommand(mock_di_container, fp_enable_args)
    result = cmd.execute()

    assert result == 0
    mock_package.set_force_push.assert_called_once_with(TestConstants.DEFAULT_BRANCH, True)


def test_forcepush_disable_success(mock_di_container, mock_package, fp_disable_args):
    mock_package.set_force_push.return_value = True
    mock_di_container.package_service.get_package.return_value = mock_package

    cmd = ConfigureCommand(mock_di_container, fp_disable_args)
    result = cmd.execute()

    assert result == 0
    mock_package.set_force_push.assert_called_once_with(TestConstants.DEFAULT_BRANCH, False)


def test_forcepush_returns_failure(mock_di_container, mock_package, fp_enable_args):
    mock_package.set_force_push.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    cmd = ConfigureCommand(mock_di_container, fp_enable_args)
    result = cmd.execute()

    assert result == 1


def test_forcepush_package_not_found(mock_di_container, fp_enable_args):
    mock_di_container.package_service.get_package.return_value = None

    cmd = ConfigureCommand(mock_di_container, fp_enable_args)
    result = cmd.execute()

    assert result == 1


# ---------------------------------------------------------------------------
# validate_args
# ---------------------------------------------------------------------------


def test_forcepush_validate_requires_branch(mock_di_container, mock_package):
    args = create_mock_args()
    args.configure_action = "forcepush"
    args.forcepush_action = "enable"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.branch = None

    cmd = ConfigureCommand(mock_di_container, args)
    with pytest.raises(ValueError, match="--branch is required"):
        cmd.validate_args()


def test_fork_validate_args_does_not_require_branch(mock_di_container):
    args = create_mock_args()
    args.configure_action = "fork"
    args.fork_action = "set"
    args.package = TestConstants.DEFAULT_PROJECT_NAME
    args.parent = "parent-package"
    args.branch = None

    cmd = ConfigureCommand(mock_di_container, args)
    cmd.validate_args()  # should not raise
