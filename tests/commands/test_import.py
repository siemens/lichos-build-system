# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import importlib
from unittest.mock import Mock, patch

import pytest
from git.exc import GitCommandError

# "import" is a Python keyword, so lichoscli/commands/import.py can't be
# reached with a literal `from ... import` statement; import it dynamically.
ImportCommand = importlib.import_module("lichoscli.commands.import").ImportCommand


@pytest.fixture
def mock_import_args(mock_args):
    args = mock_args()
    args.package = "new/package/name"
    args.repository = "https://gitlab.example.com/pocs/name"
    args.type = "gbp"
    args.branch = "flocken"
    args.branch_explicitly_provided = True
    return args


@pytest.fixture
def import_command(mock_di_container, mock_import_args):
    mock_di_container.package_service.get_projects.return_value.path = "test-group/pkg"
    return ImportCommand(mock_di_container, mock_import_args)


def test_split_package_path_nested():
    subgroup, name = ImportCommand.split_package_path("new/package/name")
    assert subgroup == "new/package"
    assert name == "name"


def test_split_package_path_flat():
    subgroup, name = ImportCommand.split_package_path("name")
    assert subgroup == ""
    assert name == "name"


def test_command_initialization_sets_correct_attributes(import_command, mock_di_container):
    assert import_command.package_name == "name"
    assert import_command.subgroup == "new/package"
    assert import_command.repository == "https://gitlab.example.com/pocs/name"
    assert import_command.package_type == "gbp"
    assert import_command.branch == "flocken"
    assert import_command.di_container == mock_di_container


def test_validate_args_requires_branch(mock_di_container, mock_import_args):
    mock_import_args.branch_explicitly_provided = False
    command = ImportCommand(mock_di_container, mock_import_args)
    with pytest.raises(ValueError):
        command.validate_args()


@patch("lichoscli.commands.import.Repo.clone_from")
def test_clone_and_push_success(mock_clone_from, mock_git_repo):
    mock_repo = mock_git_repo(branch_name="main")
    mock_clone_from.return_value = mock_repo

    mock_package = Mock()
    mock_package.ssh_url_to_repo = "git@example.com:test-group/pkg/new/package/name.git"

    result = ImportCommand.clone_and_push(mock_package, "https://gitlab.example.com/pocs/name", "name", "flocken")

    assert result is True
    mock_clone_from.assert_called_once_with("https://gitlab.example.com/pocs/name", "name")
    mock_repo.remotes.origin.rename.assert_called_once_with("upstream")
    mock_repo.create_remote.assert_called_once_with("origin", "git@example.com:test-group/pkg/new/package/name.git")
    mock_repo.git.checkout.assert_called_once_with("-b", "flocken")
    mock_repo.create_remote.return_value.push.assert_called_once_with(refspec="HEAD:refs/heads/flocken")


@patch("lichoscli.commands.import.Repo.clone_from")
def test_clone_and_push_uses_https_url_as_given(mock_clone_from, mock_git_repo):
    """Source repos (PoCs, Salsa, ...) are often HTTPS-only; must not be rewritten to SSH."""
    mock_repo = mock_git_repo(branch_name="master")
    mock_clone_from.return_value = mock_repo

    mock_package = Mock()
    mock_package.ssh_url_to_repo = "git@example.com:test-group/pkg/7zip.git"

    result = ImportCommand.clone_and_push(mock_package, "https://salsa.debian.org/debian/7zip.git", "7zip", "flocken")

    assert result is True
    mock_clone_from.assert_called_once_with("https://salsa.debian.org/debian/7zip.git", "7zip")


@patch("lichoscli.commands.import.Repo.clone_from")
def test_clone_and_push_no_checkout_when_branch_matches(mock_clone_from, mock_git_repo):
    mock_repo = mock_git_repo(branch_name="flocken")
    mock_clone_from.return_value = mock_repo

    mock_package = Mock()
    mock_package.ssh_url_to_repo = "git@example.com:test-group/pkg/name.git"

    result = ImportCommand.clone_and_push(mock_package, "https://gitlab.example.com/pocs/name", "name", "flocken")

    assert result is True
    mock_repo.git.checkout.assert_not_called()


@patch("lichoscli.commands.import.Repo.clone_from")
def test_clone_and_push_clone_failure(mock_clone_from):
    mock_clone_from.side_effect = GitCommandError("git", "failed to clone")

    mock_package = Mock()
    result = ImportCommand.clone_and_push(mock_package, "https://gitlab.example.com/pocs/name", "name", "flocken")

    assert result is False


@patch("lichoscli.commands.import.Repo.clone_from")
def test_clone_and_push_push_failure(mock_clone_from, mock_git_repo):
    mock_repo = mock_git_repo(branch_name="flocken")
    mock_clone_from.return_value = mock_repo
    mock_repo.create_remote.return_value.push.side_effect = GitCommandError("git", "failed to push")

    mock_package = Mock()
    mock_package.ssh_url_to_repo = "git@example.com:test-group/pkg/name.git"

    result = ImportCommand.clone_and_push(mock_package, "https://gitlab.example.com/pocs/name", "name", "flocken")

    assert result is False


@patch.object(ImportCommand, "clone_and_push")
def test_execute_success(
    mock_clone_and_push,
    import_command,
    mock_di_container,
):
    test_package = Mock()
    test_package.web_url = "https://gitlab.example.com/test-group/pkg/new/package/name"
    test_package.protect_branch.return_value = True
    mock_di_container.package_service.get_package.return_value = None
    mock_di_container.package_service.create_package.return_value = test_package
    mock_clone_and_push.return_value = True

    with patch("os.path.exists", return_value=False):
        result = import_command.execute()

    assert result == 0
    mock_di_container.package_service.create_package.assert_called_once_with(
        name="name",
        branch="flocken",
        package_type="gbp",
        access_level="enabled",
        subgroup="new/package",
    )
    test_package.protect_branch.assert_called_once_with("flocken")
    mock_clone_and_push.assert_called_once_with(test_package, "https://gitlab.example.com/pocs/name", "name", "flocken")


def test_execute_local_package_exists(import_command):
    with patch("os.path.exists", return_value=True):
        result = import_command.execute()
    assert result == 1


def test_execute_remote_package_exists(import_command, mock_di_container, mock_gitlab_project):
    mock_di_container.package_service.get_package.return_value = mock_gitlab_project()

    with patch("os.path.exists", return_value=False):
        result = import_command.execute()

    assert result == 1


def test_execute_create_package_fails(import_command, mock_di_container):
    mock_di_container.package_service.get_package.return_value = None
    mock_di_container.package_service.create_package.return_value = None

    with patch("os.path.exists", return_value=False):
        result = import_command.execute()

    assert result == 1


@patch.object(ImportCommand, "clone_and_push")
def test_execute_clone_and_push_fails(mock_clone_and_push, import_command, mock_di_container):
    test_package = Mock()
    test_package.protect_branch.return_value = True
    mock_di_container.package_service.get_package.return_value = None
    mock_di_container.package_service.create_package.return_value = test_package
    mock_clone_and_push.return_value = False

    with patch("os.path.exists", return_value=False):
        result = import_command.execute()

    assert result == 3


def test_execute_protect_branch_fails(import_command, mock_di_container):
    test_package = Mock()
    test_package.protect_branch.return_value = False
    mock_di_container.package_service.get_package.return_value = None
    mock_di_container.package_service.create_package.return_value = test_package

    with patch("os.path.exists", return_value=False):
        result = import_command.execute()

    assert result == 2
