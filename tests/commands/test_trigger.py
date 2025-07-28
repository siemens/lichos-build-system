import unittest
from unittest.mock import Mock, patch
from lichoscli.commands.trigger import TriggerCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestTriggerCommand(unittest.TestCase):
    def setUp(self):
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}
        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.all = False
        self.command = TriggerCommand(self.pkg_handler, self.args)

    # def test_execute_with_package_triggers_single_package(self):
    #     mock_package = fixtures.create_mock_project()
    #     self.pkg_handler.get_package.return_value = mock_package
    #     self.pkg_handler.trigger_package_build.return_value = 0
    #     self.args.package = "test-package"
    #     self.args.all = False
    #     command = TriggerCommand(self.pkg_handler, self.args)
    #     result = command.execute()
    #     self.pkg_handler.get_package.assert_called_once_with("test-package", full_details=True)
    #     self.pkg_handler.trigger_package_build.assert_called_once_with(mock_package, 'main')
    #     self.assertEqual(result, 0)

    def test_execute_with_all_triggers_all_packages(self):
        mock_package1 = fixtures.create_mock_project(name="package1")
        mock_package2 = fixtures.create_mock_project(name="package2")
        mock_package1.ci_config_path = ".gitlab-ci.yml"
        mock_package2.ci_config_path = ".gitlab-ci.yml"
        self.pkg_handler.get_all_packages.return_value = [mock_package1, mock_package2]
        self.pkg_handler.trigger_package_build.return_value = 0
        self.args.package = None
        self.args.all = True
        command = TriggerCommand(self.pkg_handler, self.args)
        result = command.execute()
        self.assertEqual(result, 0)
