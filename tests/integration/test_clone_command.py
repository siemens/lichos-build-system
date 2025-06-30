"""
Integration tests for the 'clone' command.
"""

import git
from unittest.mock import patch, Mock

from lichoscli.commands.clone import CloneCommand
from tests.fixtures import TestConstants, create_mock_args


class TestCloneCommandIntegration:
    """Integration tests for the 'clone' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.mock_package = Mock()
        self.mock_package.name = TestConstants.DEFAULT_PROJECT_NAME
        self.mock_package.ssh_url_to_repo = f"git@gitlab.example.com:{TestConstants.DEFAULT_GROUP_PATH}/{TestConstants.DEFAULT_PROJECT_NAME}.git"

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_package.return_value = self.mock_package
        self.patches.append(self.pkg_handler_patcher)

        # Mock git.Repo.clone_from
        self.git_clone_patcher = patch("git.Repo.clone_from")
        self.mock_git_clone = self.git_clone_patcher.start()
        self.mock_repo = Mock()
        self.mock_repo.create_remote.return_value = Mock()
        self.mock_git_clone.return_value = self.mock_repo
        self.patches.append(self.git_clone_patcher)

        # Mock BuildUtils.get_package_name
        self.get_package_name_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name",
            return_value=TestConstants.DEFAULT_PROJECT_NAME,
        )
        self.get_package_name_patcher.start()
        self.patches.append(self.get_package_name_patcher)

        # Mock os.path.join to return predictable paths
        self.os_path_join_patcher = patch("os.path.join")
        self.mock_os_path_join = self.os_path_join_patcher.start()
        self.mock_os_path_join.return_value = (
            f"{TestConstants.DEFAULT_PROJECT_NAME}/debian/upstream/metadata"
        )
        self.patches.append(self.os_path_join_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_clone_default(self):
        """Test basic clone command with default branch"""
        # Create arguments for the clone command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)
        # The branch attribute isn't set in this case
        delattr(args, "branch")

        # Execute the command
        clone_cmd = CloneCommand(self.mock_pkg_handler, args)
        clone_cmd.execute()

        # Verify git.Repo.clone_from was called correctly
        self.mock_git_clone.assert_called_once_with(
            self.mock_package.ssh_url_to_repo, TestConstants.DEFAULT_PROJECT_NAME
        )

    def test_clone_with_branch(self):
        """Test clone command with a specific branch"""
        # Create arguments for the clone command
        branch_name = "feature/new-feature"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME, branch=branch_name
        )

        # Execute the command
        clone_cmd = CloneCommand(self.mock_pkg_handler, args)
        clone_cmd.execute()

        # Verify git.Repo.clone_from was called with branch argument
        self.mock_git_clone.assert_called_once_with(
            self.mock_package.ssh_url_to_repo,
            TestConstants.DEFAULT_PROJECT_NAME,
            branch=branch_name,
        )

    def test_clone_with_branch_fallback(self):
        """Test clone command with branch that doesn't exist (fallback to local branch)"""
        # Create arguments for the clone command
        branch_name = "non-existent-branch"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME, branch=branch_name
        )

        # Make the first clone attempt fail with GitCommandError
        git_error = git.exc.GitCommandError("git clone -b", 128)
        self.mock_git_clone.side_effect = [
            git_error,  # First call fails
            self.mock_repo,  # Second call succeeds
        ]

        # Execute the command
        clone_cmd = CloneCommand(self.mock_pkg_handler, args)
        clone_cmd.execute()

        # Verify git.Repo.clone_from was called twice, first with branch, then without
        assert self.mock_git_clone.call_count == 2

        # First call should be with branch
        call_args_list = self.mock_git_clone.call_args_list
        assert call_args_list[0][0] == (
            self.mock_package.ssh_url_to_repo,
            TestConstants.DEFAULT_PROJECT_NAME,
        )
        assert call_args_list[0][1] == {"branch": branch_name}

        # Second call should be without branch
        assert call_args_list[1][0] == (
            self.mock_package.ssh_url_to_repo,
            TestConstants.DEFAULT_PROJECT_NAME,
        )

        # Verify checkout was called to create local branch
        assert self.mock_repo.git.checkout.called
        self.mock_repo.git.checkout.assert_called_once_with("-b", branch_name)

    def test_clone_with_forked_project(self):
        """Test clone command with a forked project"""
        # Set up forked project data
        self.mock_forked_project = dict()
        self.mock_forked_project['ssh_url_to_repo'] = (
            "git@gitlab.example.com:parent-group/original-package.git"
        )
        self.mock_package.forked_from_project = self.mock_forked_project

        # Create arguments for the clone command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)
        delattr(args, "branch")

        # Execute the command
        clone_cmd = CloneCommand(self.mock_pkg_handler, args)
        clone_cmd.execute()

        # Verify git.Repo.clone_from was called
        self.mock_git_clone.assert_called_once_with(
            self.mock_package.ssh_url_to_repo, TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify that the parent remote was created
        self.mock_repo.create_remote.assert_called_once_with(
            "parent", self.mock_forked_project['ssh_url_to_repo']
        )

        # Verify that the parent remote was fetched
        assert self.mock_repo.create_remote.return_value.fetch.called
