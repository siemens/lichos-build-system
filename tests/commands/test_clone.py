import os
from unittest.mock import Mock, call, mock_open, patch

import pytest
import yaml
from git.exc import GitCommandError

from lichoscli.commands.clone import CloneCommand
from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    args = create_mock_args()
    args.package = "test-package"
    args.branch = None
    return args


@pytest.fixture
def mock_package():
    pkg = Mock()
    pkg.name = "test-package"
    pkg.ssh_url_to_repo = "git@example.com:group/test-package.git"
    pkg.forked_from_project = None
    pkg.default_branch = "main"
    pkg.is_fork = False
    pkg.parent_ssh_url_to_repo = None
    return pkg


def test_command_initialization_sets_correct_attributes(mock_di_container, mock_args):
    command = CloneCommand(mock_di_container, mock_args)

    assert command.di_container == mock_di_container
    assert command.package_name == "test-package"
    assert command.args.branch is None

    mock_args.branch = "feature-branch"
    command = CloneCommand(mock_di_container, mock_args)
    assert command.args.branch == "feature-branch"


@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_without_branch(mock_clone_from, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_di_container.package_service.get_package.return_value = mock_package

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_di_container.package_service.get_package.assert_called_once_with("test-package")
    mock_clone_from.assert_called_once_with(mock_package.ssh_url_to_repo, "test-package", branch="main")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_branch_success(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_args.branch = "feature-branch"
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_di_container.package_service.get_package.assert_called_once_with("test-package")
    mock_clone_from.assert_called_once_with(mock_package.ssh_url_to_repo, "test-package", branch="feature-branch")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_branch_failure(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_args.branch = "nonexistent-branch"
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    mock_repo = mock_git_repo()
    mock_clone_from.side_effect = [
        GitCommandError("git", "failed"),
        mock_repo,
    ]

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_di_container.package_service.get_package.assert_called_once_with("test-package")

    expected_calls = [
        call(
            mock_package.ssh_url_to_repo,
            "test-package",
            branch="nonexistent-branch",
        ),
        call(mock_package.ssh_url_to_repo, "test-package", branch="main"),
    ]
    mock_clone_from.assert_has_calls(expected_calls)

    mock_repo.git.checkout.assert_called_once_with("-b", "nonexistent-branch")

    assert result == 0


@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_forked_project(mock_clone_from, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_di_container.package_service.get_package.return_value = mock_package

    forked_project = dict()
    forked_project["ssh_url_to_repo"] = "git@example.com:upstream/original-repo.git"
    mock_package.forked_from_project = forked_project
    mock_package.is_fork = True
    mock_package.parent_ssh_url_to_repo = "git@example.com:upstream/original-repo.git"

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_repo.create_remote.assert_called_once_with("parent", "git@example.com:upstream/original-repo.git")
    parent_remote = mock_repo.create_remote.return_value
    parent_remote.fetch.assert_called_once()

    assert result == 0


@patch("lichoscli.commands.clone.Repo.clone_from")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_execute_with_upstream_metadata(
    mock_file,
    mock_os_exists,
    mock_clone_from,
    mock_di_container,
    mock_package,
    mock_args,
    mock_git_repo,
):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.side_effect = lambda path: path == "test-package/debian/upstream/metadata"
    mock_di_container.package_service.get_package.return_value = mock_package

    yaml_data = {"Repository": "https://github.com/upstream/repo.git"}
    mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(yaml_data)

    with patch("yaml.safe_load", return_value=yaml_data):
        command = CloneCommand(mock_di_container, mock_args)
        result = command.execute()

    assert any(
        call_args[0][0] == os.path.join("test-package", "debian/upstream/metadata")
        for call_args in mock_os_exists.call_args_list
    )

    upstream_remote = mock_repo.create_remote.return_value
    mock_repo.create_remote.assert_called_once_with("upstream", "https://github.com/upstream/repo.git")
    upstream_remote.fetch.assert_called_once()

    assert result == 0


@patch("lichoscli.commands.clone.Repo.clone_from")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_execute_with_upstream_metadata_no_repository(
    mock_file,
    mock_os_exists,
    mock_clone_from,
    mock_di_container,
    mock_package,
    mock_args,
    mock_git_repo,
):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.side_effect = lambda path: path == "test-package/debian/upstream/metadata"
    mock_di_container.package_service.get_package.return_value = mock_package

    yaml_data = {"OtherKey": "value"}
    mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(yaml_data)

    with patch("yaml.safe_load", return_value=yaml_data):
        command = CloneCommand(mock_di_container, mock_args)
        result = command.execute()

    assert len(mock_os_exists.call_args_list) >= 2
    mock_repo.create_remote.assert_not_called()

    assert result == 0
