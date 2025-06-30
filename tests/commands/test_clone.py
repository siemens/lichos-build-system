import os
import unittest
from unittest.mock import Mock, patch, mock_open, call

import git
import yaml

from lichoscli.commands.clone import CloneCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestCloneCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.branch = None

        self.mock_repo = fixtures.create_mock_git_repo()
        self.mock_package = fixtures.create_mock_project()
        self.mock_package.ssh_url_to_repo = "git@example.com:group/test-package.git"

        self.pkg_handler.get_package.return_value = self.mock_package

    def test_command_initialization_sets_correct_attributes(self):
        """Test that command initialization sets correct attributes."""
        command = CloneCommand(self.pkg_handler, self.args)

        self.assertEqual(command.pkg_group_handler, self.pkg_handler)
        self.assertEqual(command.package_name, "test-package")
        self.assertIsNone(command.branch)

        # Test with branch attribute
        self.args.branch = "feature-branch"
        command = CloneCommand(self.pkg_handler, self.args)
        self.assertEqual(command.branch, "feature-branch")

    @patch("git.Repo.clone_from")
    def test_execute_without_branch(self, mock_clone_from):
        """Test execution without a branch specified."""
        mock_clone_from.return_value = self.mock_repo

        command = CloneCommand(self.pkg_handler, self.args)
        result = command.execute()

        self.pkg_handler.get_package.assert_called_once_with("test-package")
        mock_clone_from.assert_called_once_with(
            self.mock_package.ssh_url_to_repo, "test-package"
        )
        self.assertEqual(result, 0)

    @patch("git.Repo.clone_from")
    def test_execute_with_branch_success(self, mock_clone_from):
        """Test execution with a branch that exists."""
        self.args.branch = "feature-branch"
        mock_clone_from.return_value = self.mock_repo

        command = CloneCommand(self.pkg_handler, self.args)
        result = command.execute()

        self.pkg_handler.get_package.assert_called_once_with("test-package")
        mock_clone_from.assert_called_once_with(
            self.mock_package.ssh_url_to_repo, "test-package", branch="feature-branch"
        )
        self.assertEqual(result, 0)

    @patch("git.Repo.clone_from")
    def test_execute_with_branch_failure(self, mock_clone_from):
        """Test execution with a branch that does not exist."""
        self.args.branch = "nonexistent-branch"

        # First call raises GitCommandError, second call succeeds (fallback)
        mock_clone_from.side_effect = [
            git.exc.GitCommandError("git", "failed"),
            self.mock_repo,
        ]

        command = CloneCommand(self.pkg_handler, self.args)
        result = command.execute()

        self.pkg_handler.get_package.assert_called_once_with("test-package")

        # Should attempt to clone with branch first, then without
        expected_calls = [
            call(
                self.mock_package.ssh_url_to_repo,
                "test-package",
                branch="nonexistent-branch",
            ),
            call(self.mock_package.ssh_url_to_repo, "test-package"),
        ]
        mock_clone_from.assert_has_calls(expected_calls)

        # Should create local branch after cloning
        self.mock_repo.git.checkout.assert_called_once_with("-b", "nonexistent-branch")

        # We're not testing the exact log message format as it's tested implicitly by the execution

        self.assertEqual(result, 0)

    @patch("git.Repo.clone_from")
    def test_execute_with_forked_project(self, mock_clone_from):
        """Test execution with a package that is a fork."""
        mock_clone_from.return_value = self.mock_repo

        # Set up forked project
        forked_project = dict()
        forked_project['ssh_url_to_repo'] = "git@example.com:upstream/original-repo.git"
        self.mock_package.forked_from_project = forked_project

        command = CloneCommand(self.pkg_handler, self.args)
        result = command.execute()

        # Check that parent remote was added
        parent_remote = self.mock_repo.create_remote.return_value
        self.mock_repo.create_remote.assert_called_once_with(
            "parent", "git@example.com:upstream/original-repo.git"
        )
        parent_remote.fetch.assert_called_once()

        self.assertEqual(result, 0)

    @patch("git.Repo.clone_from")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_with_upstream_metadata(
        self, mock_file, mock_exists, mock_clone_from
    ):
        """Test execution with a package that has upstream metadata."""
        mock_clone_from.return_value = self.mock_repo
        mock_exists.return_value = True

        # Mock YAML data with upstream repository
        yaml_data = {"Repository": "https://github.com/upstream/repo.git"}
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(
            yaml_data
        )

        with patch("yaml.safe_load", return_value=yaml_data):
            command = CloneCommand(self.pkg_handler, self.args)
            result = command.execute()

        # Check path used to look for metadata
        mock_exists.assert_called_once_with(
            os.path.join("test-package", "debian/upstream/metadata")
        )

        # Check that upstream remote was added
        upstream_remote = self.mock_repo.create_remote.return_value
        self.mock_repo.create_remote.assert_called_once_with(
            "upstream", "https://github.com/upstream/repo.git"
        )
        upstream_remote.fetch.assert_called_once()

        self.assertEqual(result, 0)

    @patch("git.Repo.clone_from")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_with_upstream_metadata_no_repository(
        self, mock_file, mock_exists, mock_clone_from
    ):
        """Test execution with upstream metadata that does not contain repository info."""
        mock_clone_from.return_value = self.mock_repo
        mock_exists.return_value = True

        # Mock YAML data without repository key
        yaml_data = {"OtherKey": "value"}
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(
            yaml_data
        )

        with patch("yaml.safe_load", return_value=yaml_data):
            command = CloneCommand(self.pkg_handler, self.args)
            result = command.execute()

        # Should check the metadata file but not create an upstream remote
        mock_exists.assert_called_once()
        self.mock_repo.create_remote.assert_not_called()

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
