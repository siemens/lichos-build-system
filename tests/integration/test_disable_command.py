"""
Integration tests for the 'disable' command.
"""

from unittest.mock import patch, Mock

from lichoscli.commands.disable import DisableCommand
from tests.fixtures import TestConstants, create_mock_args


class TestDisableCommandIntegration:
    """Integration tests for the 'disable' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.mock_package = Mock()
        self.mock_package.name = TestConstants.DEFAULT_PROJECT_NAME

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.update_package.return_value = (
            self.mock_package
        )  # Default to success
        self.patches.append(self.pkg_handler_patcher)

        # Mock BuildUtils.get_package_name
        self.get_package_name_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name",
            return_value=TestConstants.DEFAULT_PROJECT_NAME,
        )
        self.get_package_name_patcher.start()
        self.patches.append(self.get_package_name_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_disable_package_success(self):
        """Test disabling a package successfully"""
        # Create arguments for the disable command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)

        # Execute the command
        disable_cmd = DisableCommand(self.mock_pkg_handler, args)
        result = disable_cmd.execute()

        # Verify update_package was called with correct parameters
        self.mock_pkg_handler.update_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME, access_level="disabled"
        )

        # Check return code
        assert result == 0

    def test_disable_package_failure(self):
        """Test disabling a package when the operation fails"""
        # Configure mock to indicate failure
        self.mock_pkg_handler.update_package.return_value = None

        # Create arguments for the disable command
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)

        # Execute the command
        disable_cmd = DisableCommand(self.mock_pkg_handler, args)
        result = disable_cmd.execute()

        # Verify update_package was called
        self.mock_pkg_handler.update_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME, access_level="disabled"
        )

        # Check return code (failure)
        assert result == 1

    def test_disable_package_no_name(self):
        """Test disabling a package without specifying package name"""
        # Set BuildUtils.get_package_name to return None
        self.get_package_name_patcher.stop()
        self.get_package_name_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name", return_value=None
        )
        self.get_package_name_patcher.start()
        self.patches.append(self.get_package_name_patcher)

        # Create arguments for the disable command
        args = create_mock_args(package=None)

        # Execute the command
        disable_cmd = DisableCommand(self.mock_pkg_handler, args)
        result = disable_cmd.execute()

        # Verify update_package was not called
        self.mock_pkg_handler.update_package.assert_not_called()

        # Check return code (failure)
        assert result == 1
