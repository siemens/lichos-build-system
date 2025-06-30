import unittest
from unittest.mock import Mock, patch
from lichoscli.commands.workspace import WorkspaceCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestWorkspaceCommand(unittest.TestCase):
    def setUp(self):
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}
        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.args = Mock()
        self.args.workspace_branch = "flocken"
        self.args.action = "enter"
        self.mock_package = fixtures.create_mock_project()
        self.mock_package.default_branch = "main"
        self.pkg_handler.get_package.return_value = self.mock_package

    def test_command_initialization_sets_correct_attributes(self):
        command = WorkspaceCommand(self.pkg_handler, self.args)
        self.assertEqual(command.pkg_group_handler, self.pkg_handler)

    @patch("lichoscli.commands.workspace.GitUtils")
    @patch("lichoscli.commands.workspace.os")
    @patch("lichoscli.commands.workspace.subprocess.run")
    def test_execute_enter_sets_env_and_runs_shell(
        self, mock_subprocess, mock_os, mock_gitutils
    ):
        mock_repo = Mock()
        mock_branch = Mock()
        mock_branch.name = "main"
        mock_repo.active_branch = mock_branch
        mock_gitutils.get_git_repo.return_value = mock_repo
        mock_gitutils.get_package_name.return_value = "test-package"
        mock_os.getcwd.return_value = "/tmp"
        self.args.workspace_branch = None
        self.args.branch = None
        command = WorkspaceCommand(self.pkg_handler, self.args)
        command.execute()
        mock_subprocess.assert_called()
        # Check that the environment variable was set
        mock_os.environ.__setitem__.assert_any_call("LICHOS_BRANCH", "main")

    @patch("lichoscli.commands.workspace.GitUtils")
    @patch("lichoscli.commands.workspace.os")
    @patch("lichoscli.commands.workspace.subprocess.run")
    def test_execute_no_repo_logs_error_and_returns_1(
        self, mock_subprocess, mock_os, mock_gitutils
    ):
        mock_gitutils.get_git_repo.return_value = None
        mock_gitutils.get_package_name.return_value = "test-package"
        mock_os.getcwd.return_value = "/tmp"
        self.args.workspace_branch = None
        self.args.branch = None
        command = WorkspaceCommand(self.pkg_handler, self.args)
        result = command.execute()
        self.assertEqual(result, 1)
        mock_subprocess.assert_not_called()
