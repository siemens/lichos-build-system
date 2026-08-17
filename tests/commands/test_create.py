# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

import pytest

from lichoscli.commands.create import CreateCommand


@pytest.fixture
def mock_create_args(mock_args):
    args = mock_args()
    args.package = "test-package"
    args.type = "gbp"
    args.branch = "main"
    args.subgroup = ""
    return args


@pytest.fixture
def create_command(mock_di_container, mock_create_args):
    mock_di_container.package_service.get_projects.return_value.path = "test-group/pkg"
    return CreateCommand(mock_di_container, mock_create_args)


def test_command_initialization_sets_correct_attributes(create_command, mock_di_container, mock_create_args):
    assert create_command.package_name == "test-package"
    assert create_command.package_type == "gbp"
    assert create_command.branch == "main"
    assert create_command.di_container == mock_di_container


@patch("lichoscli.commands.create.Repo.clone_from")
def test_initialize_package_repository(mock_git):
    mock_package = Mock()
    mock_package.ssh_url_to_repo = "git@example.com:test/repo.git"

    mock_repo = Mock()
    mock_author = Mock()
    mock_commit = Mock()
    mock_commit.author = mock_author
    mock_repo.index.commit.return_value = mock_commit
    mock_git.return_value = mock_repo

    author, repo = CreateCommand.initialize_package_repository(mock_package, "test-package")
    assert author == mock_author
    assert repo == mock_repo
    mock_git.assert_called_once_with("git@example.com:test/repo.git", "test-package")


@patch("os.makedirs")
@patch("builtins.open", create=True)
def test_create_debian_package_template(mock_open, mock_makedirs, mock_author):
    test_author = mock_author()

    CreateCommand.create_debian_package_template("test-package", test_author)

    mock_makedirs.assert_called()
    assert mock_open.call_count == 3


@patch("builtins.open", create=True)
def test_add_default_debian_control(mock_open, mock_author):
    mock_file = Mock()
    mock_open.return_value.__enter__.return_value = mock_file
    test_author = mock_author()

    CreateCommand.add_default_debian_control("test-package", test_author, "/path/to/control")

    mock_open.assert_called_once_with("/path/to/control", "w", encoding="utf-8")
    written_content = mock_file.write.call_args[0][0]
    assert "test-package" in written_content
    assert "Test Author" in written_content
    assert "test@example.com" in written_content


@patch("builtins.open", create=True)
def test_add_default_debian_rules(mock_open):
    mock_file = Mock()
    mock_open.return_value.__enter__.return_value = mock_file

    CreateCommand.add_default_debian_rules("/path/to/rules")

    mock_open.assert_called_once_with("/path/to/rules", "w", encoding="utf-8")
    written_content = mock_file.write.call_args[0][0]
    assert "#!/usr/bin/make -f" in written_content
    assert "dh $@" in written_content


@patch("lichoscli.commands.create.BuildUtils.check_local_package_exists")
def test_execute_local_package_exists(mock_check_local, create_command):
    mock_check_local.return_value = True

    result = create_command.execute()
    assert result == 1
    mock_check_local.assert_called_once_with("test-package")


@patch("lichoscli.commands.create.BuildUtils.check_local_package_exists")
def test_execute_remote_package_exists(mock_check_local, create_command, mock_di_container, mock_gitlab_project):
    mock_check_local.return_value = False
    mock_di_container.package_service.get_package.return_value = mock_gitlab_project()

    result = create_command.execute()
    assert result == 1
    mock_di_container.package_service.get_package.assert_called_once_with("test-package")


@patch("lichoscli.commands.create.BuildUtils.check_local_package_exists")
def test_execute_success(
    mock_check_local,
    create_command,
    mock_di_container,
    mock_author,
):
    mock_check_local.return_value = False
    mock_di_container.package_service.get_package.return_value = None

    test_package = Mock()
    test_package.web_url = "https://gitlab.example.com/test-group/pkg/test-package"
    test_package.protect_branch.return_value = True
    mock_di_container.package_service.create_package.return_value = test_package

    test_author = mock_author()
    test_repo = Mock()

    with patch.object(
        CreateCommand, "initialize_package_repository", return_value=(test_author, test_repo)
    ) as mock_init_repo, patch.object(CreateCommand, "create_debian_package_template") as mock_create_debian:
        result = create_command.execute()

    assert result == 0
    mock_di_container.package_service.create_package.assert_called_once_with(
        name="test-package",
        branch="main",
        package_type="gbp",
        access_level="enabled",
        subgroup="",
    )
    test_package.protect_branch.assert_called_once_with("main")
    mock_init_repo.assert_called_once_with(test_package, "test-package")
    mock_create_debian.assert_called_once_with("test-package", test_author)


@patch("lichoscli.commands.create.BuildUtils.check_local_package_exists")
def test_execute_create_package_fails(mock_check_local, create_command, mock_di_container):
    mock_check_local.return_value = False
    mock_di_container.package_service.get_package.return_value = None
    mock_di_container.package_service.create_package.return_value = None

    result = create_command.execute()
    assert result == 1


@patch("lichoscli.commands.create.BuildUtils.check_local_package_exists")
def test_execute_protect_branch_fails(mock_check_local, create_command, mock_di_container):
    mock_check_local.return_value = False
    mock_di_container.package_service.get_package.return_value = None

    test_package = Mock()
    test_package.protect_branch.return_value = False
    mock_di_container.package_service.create_package.return_value = test_package

    result = create_command.execute()
    assert result == 2
