"""
Integration tests for the 'show' command.
"""

import sys
import io
from unittest.mock import patch, Mock
from datetime import datetime, timezone
from contextlib import contextmanager

from lichoscli.commands.show import ShowCommand
from tests.fixtures import create_mock_args


@contextmanager
def capture_stdout():
    """
    Context manager that captures stdout.
    Returns the StringIO object containing the captured output.
    Note: Use pytest's -s flag when running to actually see the output in console.
    """
    output_capture = io.StringIO()
    original_stdout = sys.stdout
    try:
        sys.stdout = output_capture
        yield output_capture
    finally:
        sys.stdout = original_stdout
        # Print the captured output so it can be seen in the console when using pytest -s
        print("\n----- Captured Output -----")
        print(output_capture.getvalue())
        print("---------------------------")


class TestShowCommandIntegration:
    """Integration tests for the 'show' command"""

    class TeeOutput:
        """A class that captures output but also allows it to pass through to the console."""

        def __init__(self, original_stdout, capture_buffer):
            self.original_stdout = original_stdout
            self.capture_buffer = capture_buffer

        def write(self, data):
            self.capture_buffer.write(data)
            self.original_stdout.write(data)

        def flush(self):
            self.capture_buffer.flush()
            self.original_stdout.flush()

    def create_tee_output(self):
        """Creates a TeeOutput object to capture and display output."""
        output_capture = io.StringIO()
        return self.TeeOutput(sys.stdout, output_capture), output_capture

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Set up mock packages
        self.mock_package = Mock()
        self.mock_package.id = 123
        self.mock_package.path = "test-package"
        self.mock_package.builds_access_level = "enabled"
        self.mock_package.default_branch = "main"
        self.mock_package.ci_config_path = ".lichos-ci.yml"
        self.mock_package.attributes = {}

        # Create a forked package version
        self.mock_forked_package = Mock()
        self.mock_forked_package.id = 456
        self.mock_forked_package.path = "forked-package"
        self.mock_forked_package.builds_access_level = "enabled"
        self.mock_forked_package.default_branch = "main"
        self.mock_forked_package.ci_config_path = ".lichos-ci.yml"
        self.mock_forked_package.attributes = {
            "forked_from_project": {"path_with_namespace": "original/project-path"}
        }

        # Set up branches
        self.mock_branch1 = Mock()
        self.mock_branch1.name = "main"
        self.mock_branch1.protected = True
        self.mock_branch1.commit = {
            "id": "abc1234567890",
            "committed_date": "2023-01-01T12:00:00Z",
        }

        self.mock_branch2 = Mock()
        self.mock_branch2.name = "develop"
        self.mock_branch2.protected = False
        self.mock_branch2.commit = {
            "id": "def1234567890",
            "committed_date": "2023-01-02T14:30:00Z",
        }

        # Set up branches as a property of the package
        self.mock_package.branches = Mock()
        self.mock_package.branches.list = Mock(
            return_value=[self.mock_branch1, self.mock_branch2]
        )

        self.mock_forked_package.branches = Mock()
        self.mock_forked_package.branches.list = Mock(return_value=[self.mock_branch1])

        # Package with no branches
        self.mock_package_no_branches = Mock()
        self.mock_package_no_branches.id = 789
        self.mock_package_no_branches.path = "no-branches-package"
        self.mock_package_no_branches.builds_access_level = "enabled"
        self.mock_package_no_branches.default_branch = "main"
        self.mock_package_no_branches.ci_config_path = ".lichos-ci.yml"
        self.mock_package_no_branches.attributes = {}
        self.mock_package_no_branches.branches = Mock()
        self.mock_package_no_branches.branches.list = Mock(return_value=[])

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_package.side_effect = lambda pkg_name, full_details=False: {
            "test-package": self.mock_package,
            "forked-package": self.mock_forked_package,
            "no-branches-package": self.mock_package_no_branches,
        }.get(pkg_name)
        self.patches.append(self.pkg_handler_patcher)

        # Mock get_type_from_ci_path
        self.ci_utils_patcher = patch(
            "lichoscli.utils.CIConfigUtils.get_type_from_ci_path", return_value="gbp"
        )
        self.ci_utils_patcher.start()
        self.patches.append(self.ci_utils_patcher)

        # Mock package name resolver
        self.pkg_util_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name", side_effect=lambda x: x
        )
        self.pkg_util_patcher.start()
        self.patches.append(self.pkg_util_patcher)

        # Mock isoparse for the branch age calculation
        self.isoparse_patcher = patch("dateutil.parser.isoparse")
        self.mock_isoparse = self.isoparse_patcher.start()
        self.mock_isoparse.side_effect = lambda date_str: {
            "2023-01-01T12:00:00Z": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            "2023-01-02T14:30:00Z": datetime(
                2023, 1, 2, 14, 30, 0, tzinfo=timezone.utc
            ),
        }.get(date_str, datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        self.patches.append(self.isoparse_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def print_command_details(self, command_name, args):
        """Print details about the command being executed"""
        print("\n----- Command Details -----")
        print(f"Command: lichos {command_name} {args.package}")
        print("Arguments:")

        # Define the CLI arguments we care about
        cli_args = [
            "project",
            "package",
            "branch",
            "branches",
            "dry",
            "debug",
            "verbose",
            "host",
            "dump",
        ]

        # Print only relevant CLI arguments
        for key in cli_args:
            if hasattr(args, key):
                value = getattr(args, key)
                print(f"  {key}: {value}")

        print("---------------------------\n")

    def test_show_package_info(self):
        """Test showing package info"""
        # Create a datetime class with a fixed now method
        datetime_mock = Mock(wraps=datetime)
        datetime_mock.now = Mock(
            return_value=datetime(2023, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        )

        # Use our context manager that captures output
        with capture_stdout() as output_capture:
            # Replace the real datetime in the lichoscli.commands.show module
            with patch("lichoscli.commands.show.datetime", datetime_mock):
                # Create and execute the show command directly
                args = create_mock_args()
                args.package = "test-package"
                args.branches = False

                # Print the command details
                self.print_command_details("show", args)

                command = ShowCommand(self.mock_pkg_handler, args)
                result = command.execute()

                # Get captured output
                output = output_capture.getvalue()

                # Verify command executed successfully
                assert result == 0

                # Verify output contains expected information
                assert "Setting" in output
                assert "Value" in output
                assert "123" in output  # ID
                assert "test-package" in output  # Path
                assert "enabled" in output  # builds_access_level
                assert "main" in output  # default_branch

                # Verify no fork information (this is not a forked package)
                assert "forked_from_project" not in output

    def test_show_forked_package_info(self):
        """Test showing package info for a forked package"""
        # Use our context manager that captures output
        with capture_stdout() as output_capture:
            # Create and execute the show command for a forked package
            args = create_mock_args()
            args.package = "forked-package"
            args.branches = False

            # Print the command details
            self.print_command_details("show", args)

            command = ShowCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = output_capture.getvalue()

            # Verify command executed successfully
            assert result == 0

            # Verify output contains fork information
            assert "forked_from_project" in output
            assert "original/project-path" in output

    def test_show_branches(self):
        """Test showing branches of a package"""
        # Create a datetime class with a fixed now method
        datetime_mock = Mock(wraps=datetime)
        datetime_mock.now = Mock(
            return_value=datetime(2023, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        )

        # Use our context manager that captures output
        with capture_stdout() as output_capture:
            # Replace the real datetime in the lichoscli.commands.show module
            with patch("lichoscli.commands.show.datetime", datetime_mock):
                # Create and execute the show command with branches flag
                args = create_mock_args()
                args.package = "test-package"
                args.branches = True

                # Print the command details
                self.print_command_details("show", args)

                command = ShowCommand(self.mock_pkg_handler, args)
                result = command.execute()

                # Get captured output
                output = output_capture.getvalue()

                # Verify command executed successfully
                assert result == 0

                # Verify output contains expected branch information
                assert "SHA" in output
                assert "Age (days)" in output
                assert "Protected" in output
                assert "Name" in output
                assert "abc1234" in output  # shortened SHA
                assert "def1234" in output  # shortened SHA
                assert "main" in output
                assert "develop" in output
                assert "True" in output  # protected flag
                assert "False" in output  # protected flag

                # Verify age in days calculation appears (exact values depend on mocked date)
                assert (
                    "8" in output
                )  # Age of main branch (shown as 8 days in actual output)
                assert (
                    "7" in output
                )  # Age of develop branch (shown as 7 days in actual output)

    def test_show_package_not_found(self):
        """Test show command when package is not found"""
        # Use our context manager that captures output
        with capture_stdout() as output_capture:
            # Create and execute the show command with non-existent package
            args = create_mock_args()
            args.package = "nonexistent-package"
            args.branches = False

            # Print the command details
            self.print_command_details("show", args)

            command = ShowCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = output_capture.getvalue()

            # Verify command failed with appropriate exit code
            assert result == 1

            # Verify error message is present
            assert "not found" in output

    def test_show_package_with_no_branches(self):
        """Test showing branches when package has no branches"""
        # Use our context manager that captures output
        with capture_stdout() as output_capture:
            # Create and execute the show command with branches flag
            args = create_mock_args()
            args.package = "no-branches-package"
            args.branches = True

            # Print the command details
            self.print_command_details("show", args)

            command = ShowCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = output_capture.getvalue()

            # Verify command failed with appropriate exit code
            assert result == 1

            # Verify error message is present
            assert "No branches found" in output
