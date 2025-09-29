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


@patch("os.path.exists")
def test_check_local_package_exists_true(mock_os_exists):
    mock_os_exists.return_value = True
    result = CreateCommand.check_local_package_exists("test-package")
    assert result is True
    mock_os_exists.assert_called_once_with("test-package")


@patch("os.path.exists")
def test_check_local_package_exists_false(mock_os_exists):
    mock_os_exists.return_value = False
    result = CreateCommand.check_local_package_exists("test-package")
    assert result is False
    mock_os_exists.assert_called_once_with("test-package")


def test_check_remote_package_exists_true(mock_di_container, mock_gitlab_project):
    mock_di_container.package_service.get_package.return_value = mock_gitlab_project

    result = CreateCommand.check_remote_package_exists(
        mock_di_container.package_service, "existing-package", "test-group/pkg"
    )
    assert result is True
    mock_di_container.package_service.get_package.assert_called_once_with("existing-package")


def test_check_remote_package_exists_false(mock_di_container):
    mock_di_container.package_service.get_package.return_value = None

    result = CreateCommand.check_remote_package_exists(
        mock_di_container.package_service, "new-package", "test-group/pkg"
    )
    assert result is False
    mock_di_container.package_service.get_package.assert_called_once_with("new-package")


def test_create_package_success(mock_di_container, mock_gitlab_project):
    mock_di_container.package_service.create_package.return_value = mock_gitlab_project

    result = CreateCommand.create_package(
        mock_di_container.package_service,
        "test-package",
        "main",
        "gbp",
        subgroup="",
        group_rpath="test-group/pkg",
    )
    assert result == mock_gitlab_project
    mock_di_container.package_service.create_package.assert_called_once_with(
        name="test-package",
        branch="main",
        package_type="gbp",
        access_level="enabled",
        subgroup="",
    )


def test_create_subpackage_success(mock_di_container, mock_gitlab_project):
    # Configure the mock project for subpackage
    mock_gitlab_project.namespace = {
        "full_path": "test-group/pkg/subgroup",
        "path": "subgroup",
    }
    mock_di_container.package_service.create_package.return_value = mock_gitlab_project

    result = CreateCommand.create_package(
        mock_di_container.package_service,
        "test-package",
        "main",
        "gbp",
        "subgroup",
        "test-group/pkg",
    )
    assert result == mock_gitlab_project
    mock_di_container.package_service.create_package.assert_called_once_with(
        name="test-package",
        branch="main",
        package_type="gbp",
        access_level="enabled",
        subgroup="subgroup",
    )


def test_create_package_failure(mock_di_container):
    mock_di_container.package_service.create_package.return_value = None

    result = CreateCommand.create_package(
        mock_di_container.package_service,
        "test-package",
        "main",
        "gbp",
        "",
        "test-group/pkg",
    )
    assert result is None


@patch("lichoscli.commands.create.GitUtils.delete_main_from_branch_name")
def test_protect_branch_success(mock_delete_main):
    mock_package = Mock()
    mock_package.protectedbranches.create.return_value = True
    mock_delete_main.return_value = "formatted-branch"

    result = CreateCommand.protect_branch(mock_package, "main")
    assert result is True
    mock_package.protectedbranches.create.assert_called_once_with({"name": "formatted-branch"})


@patch("lichoscli.commands.create.GitUtils.delete_main_from_branch_name")
def test_protect_branch_failure(mock_delete_main):
    from lichoscli.core.exceptions import ProjectFetchingError

    mock_package = Mock()
    mock_package.protectedbranches.create.side_effect = ProjectFetchingError("Failed")
    mock_delete_main.return_value = "formatted-branch"

    result = CreateCommand.protect_branch(mock_package, "main")
    assert result is False


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


@patch.object(CreateCommand, "check_local_package_exists")
def test_execute_local_package_exists(mock_check_local, create_command):
    mock_check_local.return_value = True

    result = create_command.execute()
    assert result == 1
    mock_check_local.assert_called_once_with("test-package")


@patch.object(CreateCommand, "check_local_package_exists")
@patch.object(CreateCommand, "check_remote_package_exists")
def test_execute_remote_package_exists(mock_check_remote, mock_check_local, create_command):
    mock_check_local.return_value = False
    mock_check_remote.return_value = True

    result = create_command.execute()
    assert result == 1
    mock_check_remote.assert_called_once_with(create_command.package_service, "test-package", "test-group/pkg")


@patch.object(CreateCommand, "check_local_package_exists")
@patch.object(CreateCommand, "check_remote_package_exists")
@patch.object(CreateCommand, "create_package")
@patch.object(CreateCommand, "protect_branch")
@patch.object(CreateCommand, "initialize_package_repository")
@patch.object(CreateCommand, "create_debian_package_template")
def test_execute_success(
    mock_create_debian,
    mock_init_repo,
    mock_protect,
    mock_create_pkg,
    mock_check_remote,
    mock_check_local,
    create_command,
    mock_di_container,
    mock_gitlab_project,
    mock_author,
):
    mock_check_local.return_value = False
    mock_check_remote.return_value = False

    test_gitlab_project = mock_gitlab_project()
    mock_create_pkg.return_value = test_gitlab_project
    mock_protect.return_value = True

    test_author = mock_author()
    test_repo = Mock()
    mock_init_repo.return_value = (test_author, test_repo)

    result = create_command.execute()
    assert result == 0

    mock_check_local.assert_called_once_with("test-package")
    mock_check_remote.assert_called_once_with(create_command.package_service, "test-package", "test-group/pkg")
    mock_create_pkg.assert_called_once_with(
        create_command.package_service,
        "test-package",
        "main",
        "gbp",
        "",
        "test-group/pkg",
    )
    mock_protect.assert_called_once_with(test_gitlab_project, "main")
    mock_init_repo.assert_called_once_with(test_gitlab_project, "test-package")
    mock_create_debian.assert_called_once_with("test-package", test_author)


@patch.object(CreateCommand, "check_local_package_exists")
@patch.object(CreateCommand, "check_remote_package_exists")
@patch.object(CreateCommand, "create_package")
def test_execute_create_package_fails(
    mock_create_pkg,
    mock_check_remote,
    mock_check_local,
    create_command,
    mock_di_container,
):
    mock_check_local.return_value = False
    mock_check_remote.return_value = False
    mock_create_pkg.return_value = None

    result = create_command.execute()
    assert result == 1


@patch.object(CreateCommand, "check_local_package_exists")
@patch.object(CreateCommand, "check_remote_package_exists")
@patch.object(CreateCommand, "create_package")
@patch.object(CreateCommand, "protect_branch")
def test_execute_protect_branch_fails(
    mock_protect,
    mock_create_pkg,
    mock_check_remote,
    mock_check_local,
    create_command,
    mock_di_container,
    mock_gitlab_project,
):
    mock_check_local.return_value = False
    mock_check_remote.return_value = False
    mock_create_pkg.return_value = mock_gitlab_project
    mock_protect.return_value = False

    result = create_command.execute()
    assert result == 2
