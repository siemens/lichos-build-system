"""
Integration tests for the 'browse' command.
"""

import git
from unittest.mock import patch, Mock

from lichoscli.commands.browse import BrowseCommand
from tests.fixtures import TestConstants, create_mock_args


class TestBrowseCommandIntegration:
    """Integration tests for the 'browse' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.mock_package = Mock()
        self.mock_package.name = TestConstants.DEFAULT_PROJECT_NAME
        self.mock_package.web_url = f"https://gitlab.example.com/{TestConstants.DEFAULT_GROUP_PATH}/{TestConstants.DEFAULT_PROJECT_NAME}"

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_package.return_value = self.mock_package
        self.patches.append(self.pkg_handler_patcher)

        # Mock git.Repo
        self.git_repo_patcher = patch("git.Repo")
        self.mock_repo_class = self.git_repo_patcher.start()
        self.mock_repo = self.mock_repo_class.return_value
        self.mock_head = Mock()
        self.mock_ref = Mock()
        self.mock_ref.__str__ = lambda x: TestConstants.DEFAULT_BRANCH
        self.mock_head.reference = self.mock_ref
        self.mock_repo.head = self.mock_head
        self.patches.append(self.git_repo_patcher)

        # Mock BuildUtils.get_package_name
        self.get_package_name_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name",
            return_value=TestConstants.DEFAULT_PROJECT_NAME,
        )
        self.get_package_name_patcher.start()
        self.patches.append(self.get_package_name_patcher)

        # Mock subprocess.run
        self.subprocess_patcher = patch("subprocess.run")
        self.mock_subprocess_run = self.subprocess_patcher.start()
        self.mock_subprocess_run.return_value = Mock(returncode=0)
        self.patches.append(self.subprocess_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_browse_with_default_branch(self):
        """Test browse command using git repo's default branch"""
        # Create arguments for the browse command without branch
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)
        # Instead of removing branch attribute, set it to None
        args.branch = None

        # Execute the command
        browse_cmd = BrowseCommand(self.mock_pkg_handler, args)
        result = browse_cmd.execute()

        # Verify package was retrieved
        self.mock_pkg_handler.get_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify git repo was checked for current branch
        self.mock_repo_class.assert_called_once_with(".")

        # Verify browser was opened with correct URL
        expected_url = (
            f"{self.mock_package.web_url}/tree/{TestConstants.DEFAULT_BRANCH}"
        )
        self.mock_subprocess_run.assert_called_once_with(
            ("xdg-open", expected_url), check=True
        )

        # Check return code
        assert result == 0

    def test_browse_with_specified_branch(self):
        """Test browse command with a specific branch provided"""
        # Create arguments for the browse command with branch
        branch_name = "feature/new-feature"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME, branch=branch_name
        )

        # Execute the command
        browse_cmd = BrowseCommand(self.mock_pkg_handler, args)
        result = browse_cmd.execute()

        # Verify package was retrieved
        self.mock_pkg_handler.get_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify git repo was NOT checked since branch was provided
        self.mock_repo_class.assert_not_called()

        # Verify browser was opened with correct URL
        expected_url = f"{self.mock_package.web_url}/tree/{branch_name}"
        self.mock_subprocess_run.assert_called_once_with(
            ("xdg-open", expected_url), check=True
        )

        # Check return code
        assert result == 0

    def test_browse_package_not_found(self):
        """Test browse command when package is not found"""
        # Configure mock to indicate package not found
        self.mock_pkg_handler.get_package.return_value = None

        # Create arguments for the browse command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)
        args.branch = None

        # Execute the command
        browse_cmd = BrowseCommand(self.mock_pkg_handler, args)
        result = browse_cmd.execute()

        # Verify package lookup was attempted
        self.mock_pkg_handler.get_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify no further actions were taken
        self.mock_repo_class.assert_not_called()
        self.mock_subprocess_run.assert_not_called()

        # Check return code (failure)
        assert result == 1

    def test_browse_invalid_git_repository(self):
        """Test browse command when current directory is not a git repository"""
        # Configure git.Repo to raise InvalidGitRepositoryError
        self.mock_repo_class.side_effect = git.exc.InvalidGitRepositoryError()

        # Create arguments for the browse command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)
        args.branch = None

        # Execute the command
        browse_cmd = BrowseCommand(self.mock_pkg_handler, args)
        result = browse_cmd.execute()

        # Verify package was retrieved
        self.mock_pkg_handler.get_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify git repo check was attempted
        self.mock_repo_class.assert_called_once_with(".")

        # Verify no browser was opened
        self.mock_subprocess_run.assert_not_called()

        # Check return code (failure)
        assert result == 1
