"""
Integration tests for the 'list' command.
"""

import io
from unittest.mock import patch, Mock

from lichoscli.commands.list import ListCommand
from tests.fixtures import TestConstants, create_mock_args
from tests.mocks import MockGitLabProject


class TestListCommandIntegration:
    """Integration tests for the 'list' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.mock_packages = []
        id=1
        for pkg_name in TestConstants.SAMPLE_PROJECTS:
            mock_pkg = MockGitLabProject(name=pkg_name, id=id, ci_config_path="gbp.yml@your-group/platform-os/pkg/00ci")
            self.mock_packages.append(mock_pkg)
            id += 1

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_all_packages.return_value = self.mock_packages
        self.patches.append(self.pkg_handler_patcher)

        # Mock GitUtils methods
        self.get_group_patcher = patch(
            "lichoscli.utils.GitUtils.get_group",
            return_value=TestConstants.DEFAULT_GROUP_PATH,
        )
        self.get_group_patcher.start()
        self.patches.append(self.get_group_patcher)

        self.get_branch_patcher = patch(
            "lichoscli.utils.GitUtils.get_branch",
            return_value=TestConstants.DEFAULT_BRANCH,
        )
        self.get_branch_patcher.start()
        self.patches.append(self.get_branch_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_list_command_output_format(self):
        """Test that list command output is correctly formatted"""
        # Create a mock of sys.stdout to capture output
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Create and execute the list command directly
            args = create_mock_args()
            command = ListCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = mock_stdout.getvalue()
            print(output)
            # Verify command executed successfully
            assert result == 0

            # Verify output contains the expected package names and headers
            assert "Name" in output
            assert "Type" in output
            assert "Enabled" in output
            assert "Branch" in output

            # Check each package is listed
            for pkg_name in TestConstants.SAMPLE_PROJECTS:
                assert pkg_name in output

    def test_list_command_with_empty_result(self):
        """Test list command when no packages are available"""
        # Set up empty package list
        self.mock_pkg_handler.get_all_packages.return_value = []

        # Create a mock of sys.stdout to capture output
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Create and execute the list command
            args = create_mock_args()
            command = ListCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = mock_stdout.getvalue()

            # Verify command executed successfully
            assert result == 0

            # Verify output contains headers but no package data
            assert "Name" in output
            assert "Type" in output
            assert "Enabled" in output
            assert "Branch" in output

            # Verify no package names are in the output
            for pkg_name in TestConstants.SAMPLE_PROJECTS:
                assert pkg_name not in output
