from unittest.mock import Mock, patch

import pytest

from lichoscli.commands.build import BuildCommand
from lichoscli.core.services import BuildEnvironment, ContainerResult
from lichoscli.utils import BuildUtils


@pytest.fixture
def mock_build_args(mock_args):
    test_args = mock_args()
    test_args.package = "test-package"
    test_args.architecture = "x86_64"
    test_args.script = None
    test_args.shell = False
    test_args.enable_cross = False
    test_args.profile = None
    test_args.network = None
    test_args.mount = None
    test_args.branch = None
    test_args.pkg_group = "test-group/pkg"
    test_args.editor = None
    test_args.no_cache = False
    return test_args


def test_command_initialization_sets_correct_attributes(mock_di_container, mock_package, mock_build_args):
    mock_di_container.package_service.get_package.return_value = mock_package

    command = BuildCommand(mock_di_container, mock_build_args)

    assert command.buildparam.package_name == "test-package"
    assert command.package == mock_package
    assert command.buildparam.group == "test-group/pkg"
    assert command.buildparam.architecture == "amd64"
    assert command.buildparam.platform == "linux/amd64"
    assert command.buildparam.shell_mode == False
    assert command.buildparam.enable_cross == False


def test_normalize_architecture_maps_correctly():
    assert BuildUtils.normalize_architecture("x86_64") == "amd64"
    assert BuildUtils.normalize_architecture("aarch64") == "arm64"
    assert BuildUtils.normalize_architecture("unknown") == "unknown"


@patch("lichoscli.commands.build.GitUtils")
def test_create_build_config(mock_git_utils, mock_di_container, mock_package, mock_build_args):
    mock_git_utils.get_group.return_value = "test-group/pkg"

    mock_di_container.package_service.get_package.return_value = mock_package

    command = BuildCommand(mock_di_container, mock_build_args)

    # Verify build config was created correctly
    assert command.buildparam.package_name == "test-package"
    assert command.buildparam.architecture == "amd64"
    assert command.buildparam.group == "test-group/pkg"
    assert command.buildparam.shell_mode == False
    assert command.buildparam.enable_cross == False


@patch("lichoscli.commands.build.GitUtils")
def test_build_config_with_cross_compilation(mock_git_utils, mock_di_container, mock_package, mock_build_args):
    mock_build_args.enable_cross = True
    mock_git_utils.get_group.return_value = "test-group/pkg"

    mock_di_container.package_service.get_package.return_value = mock_package
    mock_package.variables.to_dict.return_value = {}

    command = BuildCommand(mock_di_container, mock_build_args)

    assert command.buildparam.enable_cross == True


@patch("lichoscli.commands.build.GitUtils")
def test_build_config_with_profile(mock_git_utils, mock_di_container, mock_package, mock_build_args):
    mock_build_args.profile = "test-profile"
    mock_git_utils.get_group.return_value = "test-group/pkg"

    mock_di_container.package_service.get_package.return_value = mock_package
    mock_package.variables.to_dict.return_value = {}

    command = BuildCommand(mock_di_container, mock_build_args)

    assert command.buildparam.profile == "test-profile"


@patch("os.unlink")
@patch("lichoscli.commands.build.GitUtils")
def test_execute_success(
    mock_git_utils,
    mock_unlink,
    mock_di_container,
    mock_package,
    mock_args,
):

    mock_git_utils.get_group.return_value = "test-group/pkg"
    mock_git_utils.get_git_repo.return_value = None

    mock_di_container.package_service.get_package.return_value = mock_package
    mock_package.variables.to_dict.return_value = {}

    # Ensure mock_args has the required attributes
    mock_args.branch = "main"
    mock_args.shell = False
    mock_args.editor = None

    mock_base_env = {"IMAGE": "test:latest", "REPO_SETUP_CMD": "setup", "BUILD_CMD": "build"}
    mock_di_container.environment_service.create_build_environment_from_config.return_value = mock_base_env

    mock_build_env = BuildEnvironment(
        variables={"IMAGE": "test:latest", "REPO_SETUP_CMD": "setup", "BUILD_CMD": "build"},
        image="test:latest",
        repo_setup_cmd="setup",
        build_cmd="build",
    )
    mock_di_container.environment_service.prepare_build_environment.return_value = mock_build_env

    mock_env_file = Mock()
    mock_env_file.name = "test.env"
    mock_di_container.environment_service.create_environment_file.return_value = mock_env_file

    mock_di_container.container_service.pull_image.return_value = 0
    mock_di_container.container_service.run_container.return_value = ContainerResult(return_code=0)

    command = BuildCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    mock_di_container.environment_service.create_build_environment_from_config.assert_called_once()
    mock_di_container.environment_service.prepare_build_environment.assert_called_once()
    mock_di_container.container_service.pull_image.assert_called_once_with("test:latest")
    mock_di_container.container_service.run_container.assert_called_once()
    mock_unlink.assert_called_once_with("test.env")


@patch("lichoscli.commands.build.GitUtils")
def test_execute_package_not_found(mock_git_utils, mock_di_container, mock_args):
    mock_git_utils.get_group.return_value = "test-group/pkg"

    mock_di_container.package_service.get_package.return_value = None

    command = BuildCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 1
