import logging
import unittest
from unittest.mock import Mock
from lichoscli.commands.enable import EnableCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestEnableCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""

        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.type = "test-type"
        self.args.ci_branch = None 

        self.command = EnableCommand(self.pkg_handler, self.args)

    def tearDown(self):
        """Clean up after each test method."""
        pass

    def test_enable_package_success_returns_zero(self):
        self.args.package = "package3"
        self.command = EnableCommand(self.pkg_handler, self.args)

        result = self.command.execute()

        self.assertEqual(result, 0)

    def test_enable_subpackage_success_returns_zero(self):
        self.args.package = "package4"
        self.command = EnableCommand(self.pkg_handler, self.args)

        result = self.command.execute()

        self.assertEqual(result, 0)

    def test_enable_package_failure_returns_one(self):
        """Test that package enable failure returns 1."""
        self.pkg_handler = fixtures.create_mock_pkg_handler()

        result = self.command.execute()

        self.assertEqual(result, 1)

    def test_command_initialization_sets_correct_attributes(self):
        """Test that command initialization sets correct attributes."""
        self.assertEqual(self.command.package_name, "test-package")
        self.assertEqual(self.command.type, "test-type")
        self.assertEqual(self.command.pkg_group_handler, self.pkg_handler)

    def test_enable_package_with_none_package_name(self):
        """Test behavior when package name is None."""
        logging.basicConfig(level=logging.ERROR)

        self.args.package = None
        command = EnableCommand(self.pkg_handler, self.args)
        result = command.execute()
        self.assertEqual(result, 1)

    def test_enable_package_with_empty_package_name(self):
        """Test behavior when package name is empty string."""
        self.args.package = ""
        command = EnableCommand(self.pkg_handler, self.args)
        result = command.execute()
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
