# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import os
from unittest.mock import Mock, call, mock_open, patch

import pytest
import yaml
from git.exc import GitCommandError

from lichoscli.commands.clone import CloneCommand
from lichoscli.core.models.git.git_url import UrlComponents
from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    args = create_mock_args()
    args.repository = "test-package"
    args.branch = None
    args.branch_explicitly_provided = False
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
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is False
    assert command.args.branch is None

    mock_args.branch = "feature-branch"
    mock_args.branch_explicitly_provided = True
    command = CloneCommand(mock_di_container, mock_args)
    assert command.args.branch == "feature-branch"


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_without_branch(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_di_container.package_service.get_package.assert_called_once_with(
        "test-package", include_archived=True
    )
    mock_clone_from.assert_called_once_with(mock_package.ssh_url_to_repo, "test-package", branch="main")
    assert result == 0


@patch("lichoscli.commands.clone.logger.warning")
@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_warns_when_cloning_archived_project(
    mock_clone_from,
    mock_os_exists,
    mock_warning,
    mock_di_container,
    mock_package,
    mock_args,
    mock_git_repo,
):
    mock_package.archived = True
    mock_clone_from.return_value = mock_git_repo()
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    result = CloneCommand(mock_di_container, mock_args).execute()

    mock_warning.assert_called_once_with("Cloning archived project '%s'", "test-package")
    assert result == 0


@patch("lichoscli.commands.clone.logger.warning")
@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_does_not_warn_for_active_project(
    mock_clone_from,
    mock_os_exists,
    mock_warning,
    mock_di_container,
    mock_package,
    mock_args,
    mock_git_repo,
):
    mock_package.archived = False
    mock_clone_from.return_value = mock_git_repo()
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    result = CloneCommand(mock_di_container, mock_args).execute()

    mock_warning.assert_not_called()
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_branch_success(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_args.branch = "feature-branch"
    mock_args.branch_explicitly_provided = True
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_di_container.package_service.get_package.assert_called_once_with(
        "test-package", include_archived=True
    )
    mock_clone_from.assert_called_once_with(mock_package.ssh_url_to_repo, "test-package", branch="feature-branch")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_branch_failure(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_args.branch = "nonexistent-branch"
    mock_args.branch_explicitly_provided = True
    mock_os_exists.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_package

    mock_repo = mock_git_repo()
    mock_clone_from.side_effect = [
        GitCommandError("git", "failed"),
        mock_repo,
    ]

    command = CloneCommand(mock_di_container, mock_args)
    result = command.execute()

    mock_di_container.package_service.get_package.assert_called_once_with(
        "test-package", include_archived=True
    )

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


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_forked_project(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
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


@patch("builtins.open", new_callable=mock_open)
@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_upstream_metadata(
    mock_clone_from,
    mock_os_exists,
    mock_file,
    mock_di_container,
    mock_package,
    mock_args,
    mock_git_repo,
):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    # First call: check if directory exists (False), Second call: check if metadata file exists (True)
    mock_os_exists.side_effect = lambda path: "debian/upstream/metadata" in path
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


@patch("builtins.open", new_callable=mock_open)
@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_upstream_metadata_no_repository(
    mock_clone_from,
    mock_os_exists,
    mock_file,
    mock_di_container,
    mock_package,
    mock_args,
    mock_git_repo,
):
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    # First call: check if directory exists (False), Second call: check if metadata file exists (True)
    mock_os_exists.side_effect = lambda path: "debian/upstream/metadata" in path
    mock_di_container.package_service.get_package.return_value = mock_package

    yaml_data = {"OtherKey": "value"}
    mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(yaml_data)

    with patch("yaml.safe_load", return_value=yaml_data):
        command = CloneCommand(mock_di_container, mock_args)
        result = command.execute()

    assert len(mock_os_exists.call_args_list) >= 2
    mock_repo.create_remote.assert_not_called()

    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_gitlab_url_without_branch(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    """Test cloning with a GitLab web URL (no branch specified) - direct clone without API"""
    mock_args.repository = "https://gitlab.example.com/group/subgroup/test-package"
    mock_args.branch = None
    mock_args.branch_explicitly_provided = False
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    
    # Configure URL parser to return parsed components
    mock_di_container.url_parser.parse_web_url.return_value = UrlComponents(
        host="gitlab.example.com",
        group="group/subgroup",
        package="test-package",
        branch=None
    )

    command = CloneCommand(mock_di_container, mock_args)
    
    # Verify URL was parsed and direct clone is enabled
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is True
    assert command.git_url == "git@gitlab.example.com:group/subgroup/test-package.git"
    
    result = command.execute()
    
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
    # Should clone directly from constructed git URL
    mock_clone_from.assert_called_once_with("git@gitlab.example.com:group/subgroup/test-package.git", "test-package")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_gitlab_url_with_branch(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    """Test cloning with a GitLab web URL that includes a branch - direct clone without API"""
    mock_args.repository = "https://gitlab.example.com/group/test-package/-/tree/feature-branch"
    mock_args.branch = None
    mock_args.branch_explicitly_provided = False
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    
    # Configure URL parser to return parsed components with branch
    mock_di_container.url_parser.parse_web_url.return_value = UrlComponents(
        host="gitlab.example.com",
        group="group",
        package="test-package",
        branch="feature-branch"
    )

    command = CloneCommand(mock_di_container, mock_args)
    
    # Verify URL was parsed and branch was extracted
    assert mock_args.branch == "feature-branch"
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is True
    
    result = command.execute()
    
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
    # Should clone directly from constructed git URL with the extracted branch
    mock_clone_from.assert_called_once_with("git@gitlab.example.com:group/test-package.git", "test-package", branch="feature-branch")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_gitlab_url_branch_override(mock_clone_from, mock_os_exists, mock_di_container, mock_package, mock_args, mock_git_repo):
    """Test that explicit --branch flag overrides branch from URL - direct clone without API"""
    mock_args.repository = "https://gitlab.example.com/group/test-package/-/tree/url-branch"
    mock_args.branch = "cli-branch"
    mock_args.branch_explicitly_provided = True
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    
    # Configure URL parser to return parsed components with branch
    mock_di_container.url_parser.parse_web_url.return_value = UrlComponents(
        host="gitlab.example.com",
        group="group",
        package="test-package",
        branch="url-branch"
    )

    command = CloneCommand(mock_di_container, mock_args)
    
    # Verify that CLI branch takes precedence (branch from URL should be ignored)
    assert mock_args.branch == "cli-branch"
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is True
    
    result = command.execute()
    
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
    # Should clone with CLI branch, not URL branch
    mock_clone_from.assert_called_once_with("git@gitlab.example.com:group/test-package.git", "test-package", branch="cli-branch")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_git_ssh_url(mock_clone_from, mock_os_exists, mock_di_container, mock_args, mock_git_repo):
    """Test cloning with a git SSH URL - direct clone without API"""
    mock_args.repository = "git@gitlab.example.com:group/test-package.git"
    mock_args.branch = None
    mock_args.branch_explicitly_provided = False
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    
    # URL parser won't recognize git URLs (returns None)
    mock_di_container.url_parser.parse_web_url.return_value = None

    command = CloneCommand(mock_di_container, mock_args)
    
    # Verify git URL was detected and direct clone is enabled
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is True
    assert command.git_url == "git@gitlab.example.com:group/test-package.git"
    
    result = command.execute()
    
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
    # Should clone directly using the provided URL
    mock_clone_from.assert_called_once_with("git@gitlab.example.com:group/test-package.git", "test-package")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_git_https_url(mock_clone_from, mock_os_exists, mock_di_container, mock_args, mock_git_repo):
    """Test cloning with a git HTTPS URL - direct clone without API"""
    mock_args.repository = "https://gitlab.example.com/group/subgroup/test-package.git"
    mock_args.branch = None
    mock_args.branch_explicitly_provided = False
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    
    # URL parser won't recognize git URLs (returns None)
    mock_di_container.url_parser.parse_web_url.return_value = None

    command = CloneCommand(mock_di_container, mock_args)
    
    # Verify git URL was detected, normalized to SSH, and direct clone is enabled
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is True
    assert command.git_url == "git@gitlab.example.com:group/subgroup/test-package.git"
    
    result = command.execute()
    
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
    # Should clone directly using the normalized SSH URL
    mock_clone_from.assert_called_once_with("git@gitlab.example.com:group/subgroup/test-package.git", "test-package")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_git_url_and_branch_flag(mock_clone_from, mock_os_exists, mock_di_container, mock_args, mock_git_repo):
    """Test cloning with a git URL and explicit branch flag - direct clone without API"""
    mock_args.repository = "git@gitlab.example.com:group/test-package.git"
    mock_args.branch = "feature-branch"
    mock_args.branch_explicitly_provided = True
    mock_repo = mock_git_repo()
    mock_clone_from.return_value = mock_repo
    mock_os_exists.return_value = False
    
    # URL parser won't recognize git URLs (returns None)
    mock_di_container.url_parser.parse_web_url.return_value = None

    command = CloneCommand(mock_di_container, mock_args)
    
    # Verify git URL was detected
    assert command.local_dir_name == "test-package"
    assert command.is_direct_clone is True
    
    result = command.execute()
    
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
    # Should clone with the specified branch
    mock_clone_from.assert_called_once_with("git@gitlab.example.com:group/test-package.git", "test-package", branch="feature-branch")
    assert result == 0


@patch("os.path.exists")
@patch("lichoscli.commands.clone.Repo.clone_from")
def test_execute_with_git_url_clone_failure(mock_clone_from, mock_os_exists, mock_di_container, mock_args, mock_git_repo):
    """Test that clone errors are properly handled for direct git URL clones"""
    mock_args.repository = "git@gitlab.example.com:group/test-package.git"
    mock_args.branch = "nonexistent-branch"
    mock_args.branch_explicitly_provided = True
    mock_os_exists.return_value = False
    
    # Simulate clone failure
    mock_clone_from.side_effect = GitCommandError("git", "failed to clone")
    
    # URL parser won't recognize git URLs (returns None)
    mock_di_container.url_parser.parse_web_url.return_value = None

    command = CloneCommand(mock_di_container, mock_args)
    
    result = command.execute()
    
    # Should return error code
    assert result == 1
    # Should NOT call package service API
    mock_di_container.package_service.get_package.assert_not_called()
