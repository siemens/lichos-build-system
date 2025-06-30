"""
Integration tests for the 'trigger' command.
"""

from unittest.mock import patch, Mock

from lichoscli.commands.trigger import TriggerCommand
from tests.fixtures import TestConstants, create_mock_args


class TestTriggerCommandIntegration:
    """Integration tests for the 'trigger' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.mock_package = Mock()
        self.mock_package.name = TestConstants.DEFAULT_PROJECT_NAME
        self.mock_package.ci_config_path = ".gitlab-ci.yml"

        # Create mock packages for all packages test
        self.mock_packages = []
        for pkg_name in TestConstants.SAMPLE_PROJECTS:
            mock_pkg = Mock()
            mock_pkg.name = pkg_name
            mock_pkg.ci_config_path = ".gitlab-ci.yml"
            self.mock_packages.append(mock_pkg)

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_package.return_value = self.mock_package
        self.mock_pkg_handler.get_all_packages.return_value = self.mock_packages
        self.mock_pkg_handler.trigger_package_build.return_value = (
            0  # Success by default
        )
        self.patches.append(self.pkg_handler_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_trigger_single_package(self):
        """Test triggering a build for a single package"""
        # Create arguments for the trigger command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME, all=False, branch=TestConstants.DEFAULT_BRANCH)

        # Execute the command
        trigger_cmd = TriggerCommand(self.mock_pkg_handler, args)
        result = trigger_cmd.execute()

        # Verify package was retrieved
        self.mock_pkg_handler.get_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify build was triggered
        self.mock_pkg_handler.trigger_package_build.assert_called_once_with(
            self.mock_package, args.branch
        )

        # Check return code
        assert result == 0

    def test_trigger_all_packages(self):
        """Test triggering builds for all packages"""
        # Create arguments for the trigger command with all=True
        args = create_mock_args(package=None, all=True)  # No specific package

        # Execute the command
        trigger_cmd = TriggerCommand(self.mock_pkg_handler, args)
        result = trigger_cmd.execute()

        # Verify all packages were retrieved
        assert self.mock_pkg_handler.get_all_packages.called

        # Verify builds were triggered for each package
        assert self.mock_pkg_handler.trigger_package_build.call_count == len(
            TestConstants.SAMPLE_PROJECTS
        )

        # Check return code
        assert result == 0

    def test_trigger_all_packages_with_failure(self):
        """Test triggering builds for all packages with one failing"""
        # Set up one package to fail triggering
        self.mock_pkg_handler.trigger_package_build.side_effect = [
            0,
            1,
            0,
        ]  # Second package fails

        # Create arguments for the trigger command with all=True
        args = create_mock_args(package=None, all=True)  # No specific package

        # Execute the command
        trigger_cmd = TriggerCommand(self.mock_pkg_handler, args)
        result = trigger_cmd.execute()

        # Verify all packages were retrieved
        assert self.mock_pkg_handler.get_all_packages.called

        # Verify builds were triggered for each package
        assert self.mock_pkg_handler.trigger_package_build.call_count == len(
            TestConstants.SAMPLE_PROJECTS
        )

        # Check that we get a non-zero return code
        assert result != 0
        assert result == 1  # One failure

    def test_trigger_no_package_specified(self):
        """Test trigger command with no package specified and --all not set"""
        # Create arguments for the trigger command with no package and all=False
        args = create_mock_args(package=None, all=False)

        # Execute the command
        trigger_cmd = TriggerCommand(self.mock_pkg_handler, args)
        result = trigger_cmd.execute()

        # Verify no builds were triggered
        assert not self.mock_pkg_handler.trigger_package_build.called

        # Check for error condition
        assert result != 0
