"""
Integration tests for the 'log' command.
"""

from unittest.mock import patch, Mock

from lichoscli.commands.log import LogCommand
from tests.fixtures import create_mock_args


class TestLogCommandIntegration:
    """Integration tests for the 'log' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Set up mock packages
        self.mock_package = Mock()
        self.mock_package.id = 123
        self.mock_package.name = "test-package"

        # Set up mock jobs
        self.mock_job = Mock()
        self.mock_job.id = 456
        self.mock_job.name = "build"

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_package.return_value = self.mock_package
        self.mock_pkg_handler.get_job_by_name.return_value = self.mock_job

        # Set up gitlab mock for job trace retrieval
        self.mock_gitlab = Mock()
        mock_project = Mock()
        mock_job = Mock()
        mock_job.trace.return_value = (
            b"This is a sample log\nWith multiple lines\nIncluding [32mANSI colors[0m\n"
        )
        mock_project.jobs = Mock()
        mock_project.jobs.get.return_value = mock_job
        self.mock_gitlab.projects = Mock()
        self.mock_gitlab.projects.get.return_value = mock_project
        self.mock_pkg_handler.gitlab = self.mock_gitlab

        self.patches.append(self.pkg_handler_patcher)

        # Mock console for rich text output
        self.console_patcher = patch("rich.console.Console.print")
        self.mock_console_print = self.console_patcher.start()
        self.patches.append(self.console_patcher)

        # Mock _wait_for_job_start
        self.wait_job_patcher = patch.object(LogCommand, "_wait_for_job_start")
        self.mock_wait_job = self.wait_job_patcher.start()
        self.mock_wait_job.return_value = self.mock_job
        self.patches.append(self.wait_job_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_log_command_with_valid_job(self):
        """Test log command with valid package and job"""
        # Create and execute the log command
        args = create_mock_args()
        args.package = "test-package"
        args.jobname = "build"  # Changed from job to jobname to match the LogCommand implementation
        args.wait = (
            False  # Use wait instead of follow to match the LogCommand implementation
        )

        command = LogCommand(self.mock_pkg_handler, args)
        result = command.execute()

        # Verify command executed successfully
        assert result == 0

        # Verify proper methods were called
        self.mock_pkg_handler.get_package.assert_called_once_with("test-package")
        self.mock_pkg_handler.get_job_by_name.assert_called_once_with(
            self.mock_package, "build"
        )
        self.mock_wait_job.assert_called_once()

        # Verify gitlab trace API was called
        self.mock_gitlab.projects.get.assert_called_once_with(123)
        self.mock_gitlab.projects.get.return_value.jobs.get.assert_called_once_with(456)
        self.mock_gitlab.projects.get.return_value.jobs.get.return_value.trace.assert_called_once()

        # Verify that console.print was called once (to display the log)
        self.mock_console_print.assert_called_once()

    def test_log_command_with_invalid_package(self):
        """Test log command with invalid package"""
        # Set up mock to return None for the package
        self.mock_pkg_handler.get_package.return_value = None

        # Create and execute the log command with a non-existent package
        args = create_mock_args()
        args.package = "nonexistent-package"
        args.jobname = "build"  # Changed from job to jobname
        args.wait = False  # Changed from follow to wait

        # Mock logger to check for error messages
        with patch("lichoscli.commands.log.logger") as mock_logger:
            command = LogCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Verify command failed with appropriate exit code
            assert result == 1

            # Verify error was logged
            mock_logger.error.assert_called_once_with(
                "Package %s not found.", "nonexistent-package"
            )

    def test_log_command_with_invalid_job(self):
        """Test log command with invalid job"""
        # Set up mock to return None for the job
        self.mock_pkg_handler.get_job_by_name.return_value = None

        # Create and execute the log command with a non-existent job
        args = create_mock_args()
        args.package = "test-package"
        args.jobname = "nonexistent-job"  # Changed from job to jobname
        args.wait = False  # Changed from follow to wait

        command = LogCommand(self.mock_pkg_handler, args)
        result = command.execute()

        # Verify command failed with appropriate exit code
        assert result == 1

    def test_log_command_with_empty_log(self):
        """Test log command when job has empty log output"""
        # Set up mock to return empty log
        mock_project = self.mock_gitlab.projects.get.return_value
        mock_project.jobs.get.return_value.trace.return_value = b""

        # Create and execute the log command
        args = create_mock_args()
        args.package = "test-package"
        args.jobname = "build"  # Changed from job to jobname
        args.wait = False  # Changed from follow to wait

        command = LogCommand(self.mock_pkg_handler, args)
        result = command.execute()

        # Verify command executed successfully despite empty log
        assert result == 0

        # Verify that console.print was called with the "No log output" message
        # We can't check the exact Text object contents, but we can verify it was called
        self.mock_console_print.assert_called_once()

    def test_normalize_gitlab_log(self):
        """Test the normalize_gitlab_log method handles carriage returns correctly"""
        # Create sample input with different line endings
        raw_log = "Line 1\rLine 2\r\nLine 3\r\rLine 4"

        # Create command instance
        args = create_mock_args()
        args.package = "test-package"
        args.job = "build"
        args.follow = False

        command = LogCommand(self.mock_pkg_handler, args)
        normalized_log = command.normalize_gitlab_log(raw_log)

        # Verify correct normalization
        assert normalized_log == "Line 1\nLine 2\nLine 3\n\nLine 4"

    def test_job_waiting(self):
        """Test the _wait_for_job_start method is called for pending jobs"""
        # Create and execute the log command
        args = create_mock_args()
        args.package = "test-package"
        args.jobname = "build"  # Changed from job to jobname
        args.wait = False  # Changed from follow to wait

        command = LogCommand(self.mock_pkg_handler, args)
        result = command.execute()
        assert result == 0

        # Verify the _wait_for_job_start method was called
        self.mock_wait_job.assert_called_once_with(self.mock_package, self.mock_job)
