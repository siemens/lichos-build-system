import unittest
from unittest.mock import Mock, patch
from lichoscli.commands.list import ListCommand
from lichoscli.commands.base import CommandRegister
from tests.mocks import MockGitLabProject
from tests import fixtures


class TestListCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""

        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()

        self.command = ListCommand(self.pkg_handler, self.args)

    def test_command_initialization_sets_correct_attributes(self):
        """Test that command initialization sets correct attributes."""
        self.assertEqual(self.command.pkg_group_handler, self.pkg_handler)

    @patch("lichoscli.commands.list.print")
    @patch("lichoscli.commands.list.tabulate")
    def test_execute_with_packages_success(self, mock_tabulate, mock_print):
        """Test successful execution with packages returns 0 and prints table."""

        mock_package1 = MockGitLabProject(name="package1", id=1, ci_config_path="gbp.yml@test-group/pkg/00ci")

        mock_package2 = MockGitLabProject(name="package2", id=2, ci_config_path="gbp.yml@test-group/pkg/00ci", default_branch="develop", builds_access_level="disabled")

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package1, mock_package2])
        mock_tabulate.return_value = "formatted_table_output"

        result = self.command.execute()

        self.assertEqual(result, 0)

        self.pkg_handler.get_all_packages.assert_called_once()

        expected_headers = ["Name", "Type", "Enabled", "Branch"]
        expected_rows = [
            ["package1", "gbp", "enabled", "main"],
            ["package2", "gbp", "disabled", "develop"],
        ]
        mock_tabulate.assert_called_once_with(expected_rows, headers=expected_headers)

        mock_print.assert_called_once_with("formatted_table_output")
    
    @patch("lichoscli.commands.list.print")
    @patch("lichoscli.commands.list.tabulate")
    def test_execute_with_subgroups(self, mock_tabulate, mock_print):
        """Test successful execution with subpackages returns 0 and prints table."""


        mock_package1 = MockGitLabProject(name="package1", id=1, ci_config_path="gbp.yml@test-group/pkg/00ci", namespace={"full_path": "test-group/pkg", "path": "pkg"})

        mock_package2 = MockGitLabProject(name="package4", id=4, ci_config_path="gbp.yml@test-group/pkg/00ci", namespace={"full_path": "test-group/pkg/subgroup", "path": "subgroup"})

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package1, mock_package2])
        mock_tabulate.return_value = "formatted_table_output"

        result = self.command.execute()

        self.assertEqual(result, 0)

        self.pkg_handler.get_all_packages.assert_called()

        expected_headers = ["Name", "Type", "Enabled", "Branch"]
        expected_rows = [
            ["package1", "gbp", "enabled", "main"],
            ["subgroup/package4", "gbp", "enabled", "main"],
        ]
        mock_tabulate.assert_called_once_with(expected_rows, headers=expected_headers)

        mock_print.assert_called_once_with("formatted_table_output")

    @patch("lichoscli.commands.list.print")
    @patch("lichoscli.commands.list.tabulate")
    def test_execute_with_empty_packages_list(self, mock_tabulate, mock_print):
        """Test execution with empty packages list."""
        self.pkg_handler.get_all_packages = Mock(return_value=[])
        mock_tabulate.return_value = "empty_table_output"

        result = self.command.execute()

        self.assertEqual(result, 0)

        self.pkg_handler.get_all_packages.assert_called_once()

        expected_headers = ["Name", "Type", "Enabled", "Branch"]
        expected_rows = []
        mock_tabulate.assert_called_once_with(expected_rows, headers=expected_headers)

        mock_print.assert_called_once_with("empty_table_output")

    @patch("lichoscli.commands.list.print")
    @patch("lichoscli.commands.list.tabulate")
    def test_execute_with_single_package(self, mock_tabulate, mock_print):
        """Test execution with single package."""
        mock_package = MockGitLabProject(name="single-package", id=1, ci_config_path="gbp.yml@test-group/pkg/00ci", default_branch="master")

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package])
        mock_tabulate.return_value = "single_package_table"

        result = self.command.execute()

        self.assertEqual(result, 0)

        expected_headers = ["Name", "Type", "Enabled", "Branch"]
        expected_rows = [["single-package", "gbp", "enabled", "master"]]
        mock_tabulate.assert_called_once_with(expected_rows, headers=expected_headers)

        mock_print.assert_called_once_with("single_package_table")

    @patch("lichoscli.commands.list.print")
    @patch("lichoscli.commands.list.tabulate")
    def test_execute_handles_package_with_none_values(self, mock_tabulate, mock_print):
        """Test execution handles packages with None attribute values gracefully."""
        mock_package = Mock()
        mock_package.name = None
        mock_package.ci_config_path = None
        mock_package.builds_access_level = None
        mock_package.default_branch = None
        mock_package.namespace = {"full_path": None, "path": None}

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package])
        mock_tabulate.return_value = "none_values_table"

        result = self.command.execute()

        self.assertEqual(result, 0)

        expected_headers = ["Name", "Type", "Enabled", "Branch"]
        expected_rows = [[None, "local", None, None]]
        mock_tabulate.assert_called_once_with(expected_rows, headers=expected_headers)


if __name__ == "__main__":
    unittest.main()
