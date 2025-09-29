import pytest

from lichoscli.commands.enable import EnableCommand
from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    args = create_mock_args()
    args.package = "test-package"
    args.type = "test-type"
    args.ci_branch = None
    return args


def test_enable_package_success_returns_zero(mock_di_container, mock_args):
    mock_args.package = "package3"
    package_service = mock_di_container.obtain_ref.return_value
    package_service.enable_package.return_value = True

    command = EnableCommand(mock_di_container, mock_args)
    result = command.execute()
    assert result == 0


def test_enable_subpackage_success_returns_zero(mock_di_container, mock_args):
    mock_args.package = "package4"
    package_service = mock_di_container.obtain_ref.return_value
    package_service.enable_package.return_value = True

    command = EnableCommand(mock_di_container, mock_args)
    result = command.execute()
    assert result == 0


def test_enable_package_failure_returns_one(mock_di_container, mock_args):
    mock_di_container.package_service.update_package.return_value = None

    command = EnableCommand(mock_di_container, mock_args)
    result = command.execute()
    assert result == 1


def test_command_initialization_sets_correct_attributes(mock_di_container, mock_args):
    command = EnableCommand(mock_di_container, mock_args)
    assert command.package_name == "test-package"
    assert command.type == "test-type"
    assert command.di_container == mock_di_container


def test_enable_package_with_none_package_name(mock_di_container, mock_args):
    mock_args.package = None
    mock_di_container.package_service.update_package.return_value = None
    command = EnableCommand(mock_di_container, mock_args)
    result = command.execute()
    assert result == 1


def test_enable_package_with_empty_package_name(mock_di_container, mock_args):
    mock_args.package = ""
    mock_di_container.package_service.update_package.return_value = None
    command = EnableCommand(mock_di_container, mock_args)
    result = command.execute()
    assert result == 1
