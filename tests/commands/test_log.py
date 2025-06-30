import unittest
from unittest.mock import Mock, patch, call
from lichoscli.commands.log import LogCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures
from rich.text import Text


class TestLogCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""

        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        # Add gitlab attribute to the mock pkg_handler if not present
        if not hasattr(self.pkg_handler, "gitlab"):
            self.pkg_handler.gitlab = Mock()

        self.args = fixtures.create_mock_args(
            package="test-package", jobname="test-job", wait=False, branch=None
        )
        self.mock_package = fixtures.create_mock_project(name="test-package", id=123)
        self.mock_job = fixtures.create_mock_job(
            id=123, status="running", name="test-job"
        )
        self.pkg_handler.get_job_by_name.return_value = self.mock_job

        self.pkg_handler.get_package.return_value = self.mock_package

        # Setup the logger mock that's actually used in the code
        self.mock_logger = Mock()
        self.logger_patcher = patch("lichoscli.commands.log.logger", self.mock_logger)
        self.logger_patcher.start()
        self.addCleanup(self.logger_patcher.stop)

        self.command = LogCommand(self.pkg_handler, self.args)

    def test_command_initialization_sets_correct_attributes(self):
        """Test that command initialization sets correct attributes."""
        self.assertEqual(self.command.package_name, "test-package")
        self.assertEqual(self.command.pkg_group_handler, self.pkg_handler)
        self.assertEqual(self.command.jobname, "test-job")
        self.assertEqual(self.command.wait, False)
        self.assertEqual(self.command.branch, None)

    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch("time.sleep")
    def test_wait_for_job_start_no_waiting_needed(
        self, mock_sleep, mock_flush, mock_write
    ):
        """Test the _wait_for_job_start method when job is already running."""
        self.mock_job.status = "running"

        result = self.command._wait_for_job_start(self.mock_package, self.mock_job)

        self.assertEqual(result, self.mock_job)
        mock_sleep.assert_not_called()
        mock_write.assert_not_called()
        mock_flush.assert_not_called()

    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch("time.sleep")
    def test_wait_for_job_start_with_wait_flag_not_set(
        self, mock_sleep, mock_flush, mock_write
    ):
        """Test the _wait_for_job_start method without wait flag even if job is pending."""
        self.mock_job.status = "pending"
        self.args.wait = False
        self.command = LogCommand(self.pkg_handler, self.args)

        result = self.command._wait_for_job_start(self.mock_package, self.mock_job)

        self.assertEqual(result, self.mock_job)
        mock_sleep.assert_not_called()
        mock_write.assert_not_called()
        mock_flush.assert_not_called()

    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch("time.sleep")
    def test_wait_for_job_start_with_waiting(self, mock_sleep, mock_flush, mock_write):
        """Test the _wait_for_job_start method with waiting for a job to start."""
        self.mock_job.status = "pending"
        self.args.wait = True
        self.command = LogCommand(self.pkg_handler, self.args)

        # Mock job status transition from pending to running
        mock_updated_job = Mock()
        mock_updated_job.id = 123
        mock_updated_job.status = "running"

        mock_project = Mock()
        mock_project.jobs = Mock()
        mock_project.jobs.get.return_value = mock_updated_job

        self.pkg_handler.gitlab.projects.get.return_value = mock_project

        result = self.command._wait_for_job_start(self.mock_package, self.mock_job)

        mock_sleep.assert_called_with(3)
        mock_write.assert_called()
        mock_flush.assert_called()
        self.assertEqual(result, mock_updated_job)
        self.pkg_handler.gitlab.projects.get.assert_called_once_with(
            self.mock_package.id
        )
        mock_project.jobs.get.assert_called_once_with(self.mock_job.id)

    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch("time.sleep")
    def test_wait_for_job_start_with_exception(
        self, mock_sleep, mock_flush, mock_write
    ):
        """Test the _wait_for_job_start method handling an exception."""
        self.mock_job.status = "pending"
        self.args.wait = True
        self.command = LogCommand(self.pkg_handler, self.args)

        # Setup exception
        self.pkg_handler.gitlab.projects.get.side_effect = Exception("Connection error")

        result = self.command._wait_for_job_start(self.mock_package, self.mock_job)

        # Verify logger was called with an error
        self.mock_logger.error.assert_called_once()
        self.assertIsNone(result)

    def test_normalize_gitlab_log(self):
        """Test normalize_gitlab_log method correctly handles carriage returns."""
        # Test with various types of line endings
        raw_log = "Line 1\rLine 2\r\nLine 3\r\rLine 4"
        normalized_log = self.command.normalize_gitlab_log(raw_log)

        expected_output = "Line 1\nLine 2\nLine 3\n\nLine 4"
        self.assertEqual(normalized_log, expected_output)

    @patch("rich.console.Console.print")
    def test_execute_successful_with_log(self, mock_console_print):
        """Test execute method successfully displays log output."""
        # Mock the job trace retrieval
        mock_job_trace = b"Sample log output\nwith multiple lines\n"

        mock_project = Mock()
        mock_project.jobs = Mock()
        mock_project.jobs.get.return_value.trace.return_value = mock_job_trace

        self.pkg_handler.gitlab.projects.get.return_value = mock_project

        with patch.object(
            self.command, "_wait_for_job_start", return_value=self.mock_job
        ):
            result = self.command.execute()

        self.assertEqual(result, 0)
        self.pkg_handler.get_package.assert_called_once_with("test-package")
        self.pkg_handler.get_job_by_name.assert_called_once_with(
            self.mock_package, "test-job"
        )
        mock_project.jobs.get.assert_called_once_with(self.mock_job.id)
        mock_console_print.assert_called_once()

    @patch("rich.console.Console.print")
    def test_execute_with_empty_log(self, mock_console_print):
        """Test execute method with empty log output."""
        # Mock the job trace retrieval with empty log
        mock_job_trace = b""

        mock_project = Mock()
        mock_project.jobs = Mock()
        mock_project.jobs.get.return_value.trace.return_value = mock_job_trace

        self.pkg_handler.gitlab.projects.get.return_value = mock_project

        with patch.object(
            self.command, "_wait_for_job_start", return_value=self.mock_job
        ):
            result = self.command.execute()

        self.assertEqual(result, 0)
        mock_console_print.assert_called_once()
        # Verify that it prints a message about no log output
        mock_console_print.assert_called_with(unittest.mock.ANY)
        text_arg = mock_console_print.call_args[0][0]
        self.assertIsInstance(text_arg, Text)
        self.assertEqual(text_arg.plain, "No log output available.")

    def test_execute_package_not_found(self):
        """Test execute method when package is not found."""
        # Setup the mock to return None for package
        self.pkg_handler.get_package.return_value = None

        result = self.command.execute()

        self.assertEqual(result, 1)
        # Verify the logger was called with correct error message
        self.mock_logger.error.assert_called_once_with(
            "Package %s not found.", "test-package"
        )

    def test_execute_job_not_found(self):
        """Test execute method when job is not found."""
        # Setup the mock to return None for job
        self.pkg_handler.get_job_by_name.return_value = None

        result = self.command.execute()

        self.assertEqual(result, 1)
        # Verify appropriate error was logged - but the code doesn't actually log anything when job is not found
        # so we're just checking the return value

    def test_execute_job_waiting_failed(self):
        """Test execute method when waiting for job fails."""
        # Mock _wait_for_job_start to return None
        with patch.object(self.command, "_wait_for_job_start", return_value=None):
            result = self.command.execute()

        self.assertEqual(result, 1)
        # Verify the logger was called with correct error message
        self.mock_logger.error.assert_called_once_with(
            "Job %s did not start.", "test-job"
        )


if __name__ == "__main__":
    unittest.main()
