import logging
import unittest
from unittest.mock import Mock
from lichoscli.commands.disable import DisableCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestDisableCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}
        # Use reusable fixtures
        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.command = DisableCommand(self.pkg_handler, self.args)

    def tearDown(self):
        pass

    def test_disable_package_success_returns_zero(self):
        # Simulate a package that can be disabled
        self.args.package = "package3"
        self.command = DisableCommand(self.pkg_handler, self.args)
        result = self.command.execute()
        self.assertEqual(result, 0)

    def test_disable_subpackage_success_returns_zero(self):
        # Simulate a subpackage that can be disabled
        self.args.package = "package4"
        self.command = DisableCommand(self.pkg_handler, self.args)
        result = self.command.execute()
        self.assertEqual(result, 0)

    def test_disable_package_failure_returns_one(self):
        # Simulate a package that cannot be disabled (not found or already disabled)
        self.args.package = "nonexistent-package"
        self.command = DisableCommand(self.pkg_handler, self.args)
        result = self.command.execute()
        self.assertEqual(result, 1)

    def test_command_initialization_sets_correct_attributes(self):
        self.assertEqual(self.command.package_name, "test-package")
        self.assertEqual(self.command.pkg_group_handler, self.pkg_handler)

    def test_disable_package_with_none_package_name(self):
        logging.basicConfig(level=logging.ERROR)
        self.args.package = None
        command = DisableCommand(self.pkg_handler, self.args)
        result = command.execute()
        self.assertEqual(result, 1)

    def test_disable_package_with_empty_package_name(self):
        self.args.package = ""
        command = DisableCommand(self.pkg_handler, self.args)
        result = command.execute()
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
