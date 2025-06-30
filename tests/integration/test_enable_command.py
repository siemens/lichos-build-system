"""
Integration tests for the 'enable' command.
"""

from unittest.mock import patch, Mock

from lichoscli.commands.enable import EnableCommand
from tests.fixtures import TestConstants, create_mock_args


class TestEnableCommandIntegration:
    """Integration tests for the 'enable' command"""

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

    def test_enable_package_success(self):
        """Test enabling a package successfully"""
        self._test_different_return_values(0)

    def test_enable_package_failure(self):
        """Test enabling a package when the operation fails"""
        # Configure mock to indicate failure
        self.mock_pkg_handler.update_package.return_value = None

        self._test_different_return_values(1)

    def _test_different_return_values(self, expected_result):
        build_type = "standard"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME, type=build_type
        )
        enable_cmd = EnableCommand(self.mock_pkg_handler, args)
        result = enable_cmd.execute()
        self.mock_pkg_handler.update_package.assert_called_once()
        called_args, called_kwargs = self.mock_pkg_handler.update_package.call_args
        assert called_args[0] == TestConstants.DEFAULT_PROJECT_NAME
        assert called_kwargs["access_level"] == "enabled"
        assert called_kwargs["ci_config_path"].startswith("standard.yml@")
        assert result == expected_result

    def test_enable_package_return_values(self):
        """Test different return values from update_package"""
        build_type = "standard"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME, type=build_type
        )

        # Case 1: update_package returns a mock package (success)
        self.mock_pkg_handler.update_package.return_value = self.mock_package
        enable_cmd = EnableCommand(self.mock_pkg_handler, args)
        result = enable_cmd.execute()
        assert result == 0

        # Case 2: update_package returns None (failure)
        self.mock_pkg_handler.update_package.reset_mock()
        self.mock_pkg_handler.update_package.return_value = None
        enable_cmd = EnableCommand(self.mock_pkg_handler, args)
        result = enable_cmd.execute()
        assert result == 1

    def test_enable_package_no_type(self):
        """Test enabling a package without specifying build type"""
        # Create arguments for the enable command without type
        args = create_mock_args(package=TestConstants.DEFAULT_PROJECT_NAME)
        args.type = None

        # Execute the command
        enable_cmd = EnableCommand(self.mock_pkg_handler, args)
        result = enable_cmd.execute()

        # Verify update_package was called with correct parameters
        self.mock_pkg_handler.update_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME, access_level="enabled", ci_config_path=None
        )

        # Check return code
        assert result == 0
