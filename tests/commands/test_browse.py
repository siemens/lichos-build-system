import unittest
from unittest.mock import Mock, patch

from gitlab import GitlabError
from lichoscli.commands.browse import BrowseCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestBrowseCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = fixtures.TestConstants.DEFAULT_PROJECT_NAME
        self.args.branch = None

        self.command = BrowseCommand(self.pkg_handler, self.args)

    @patch("lichoscli.commands.browse.GitUtils.auto_detect_git_repo")
    @patch("lichoscli.commands.browse.subprocess.run")
    def test_execute_success(self, mock_subprocess, mock_auto_detect):
        """Test successful execution of the browse command."""
        mock_package = fixtures.create_mock_project()
        mock_package.web_url = "https://example.com/package"
        self.pkg_handler.get_package = Mock(return_value=mock_package)

        mock_repo_instance = Mock()
        mock_repo_instance.head.reference = fixtures.TestConstants.DEFAULT_BRANCH
        mock_auto_detect.return_value = mock_repo_instance

        mock_subprocess.return_value.returncode = 0

        result = self.command.execute()

        self.assertEqual(result, 0)
        mock_subprocess.assert_called_once_with(
            ("xdg-open", "https://example.com/package/tree/main"), check=True
        )

    @patch("lichoscli.commands.browse.GitUtils.auto_detect_git_repo")
    def test_execute_invalid_repo(self, mock_auto_detect):
        """Test execution when the repository is invalid."""
        mock_auto_detect.side_effect = GitlabError("Invalid repository")

        result = self.command.execute()

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
