"""
Unit tests for StatusCommand
"""

from unittest.mock import patch

from lichoscli.commands.status import StatusCommand
from tests.mocks import create_mock_args


def test_init_with_package_argument(mock_di_container):
    """Test command initialization with package argument"""
    args = create_mock_args(package="test-package")
    command = StatusCommand(mock_di_container, args)

    assert command.package_name == "test-package"
    assert not command.dump


def test_init_with_no_package_argument(mock_di_container):
    """Test command initialization without package argument"""
    args = create_mock_args(package=None)
    command = StatusCommand(mock_di_container, args)

    assert command.package_name is None


def test_init_with_dump_flag(mock_di_container):
    """Test command initialization with dump flag"""
    args = create_mock_args(dump=True)
    command = StatusCommand(mock_di_container, args)

    assert command.dump


def test_execute_with_package_calls_print_package_status(mock_di_container):
    """Test execute method calls print_package_status when package is specified"""
    args = create_mock_args(package="test-package")
    command = StatusCommand(mock_di_container, args)

    with patch.object(command, "print_package_status", return_value=0) as mock_print:
        result = command.execute()

        mock_print.assert_called_once()
        assert result == 0


def test_execute_without_package_calls_print_all_status(mock_di_container):
    """Test execute method calls print_all_status when no package is specified"""
    args = create_mock_args(package=None)
    command = StatusCommand(mock_di_container, args)

    with patch.object(command, "print_all_status", return_value=0) as mock_print:
        result = command.execute()

        mock_print.assert_called_once()
        assert result == 0
