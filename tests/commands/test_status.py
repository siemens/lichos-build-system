"""
Unit tests for StatusCommand
"""

import unittest
from unittest.mock import Mock, patch
from datetime import datetime
from lichoscli.commands.status import StatusCommand
from tests import fixtures


class TestStatusCommand(unittest.TestCase):
    def setUp(self):
        self.pkg_handler = Mock()
        self.args = fixtures.create_mock_args()
        self.command = StatusCommand(self.pkg_handler, self.args)

    def test_init_with_package_argument(self):
        """Test command initialization with package argument"""
        args = fixtures.create_mock_args(package="test-package")
        command = StatusCommand(self.pkg_handler, args)
        
        self.assertEqual(command.package_name, "test-package")
        self.assertFalse(command.dump)

    def test_init_with_no_package_argument(self):
        """Test command initialization without package argument"""
        args = fixtures.create_mock_args(package=None)
        command = StatusCommand(self.pkg_handler, args)
        
        self.assertIsNone(command.package_name)

    def test_init_with_dump_flag(self):
        """Test command initialization with dump flag"""
        args = fixtures.create_mock_args(dump=True)
        command = StatusCommand(self.pkg_handler, args)
        
        self.assertTrue(command.dump)

    def test_execute_with_package_calls_print_package_status(self):
        """Test execute method calls print_package_status when package is specified"""
        args = fixtures.create_mock_args(package="test-package")
        command = StatusCommand(self.pkg_handler, args)
        
        with patch.object(command, 'print_package_status', return_value=0) as mock_print:
            result = command.execute()
            
            mock_print.assert_called_once()
            self.assertEqual(result, 0)

    def test_execute_without_package_calls_print_all_status(self):
        """Test execute method calls print_all_status when no package is specified"""
        args = fixtures.create_mock_args(package=None)
        command = StatusCommand(self.pkg_handler, args)
        
        with patch.object(command, 'print_all_status', return_value=0) as mock_print:
            result = command.execute()
            
            mock_print.assert_called_once()
            self.assertEqual(result, 0)
