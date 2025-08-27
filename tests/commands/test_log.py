import unittest
from unittest.mock import Mock, patch
from gitlab import GitlabError
from lichoscli.commands.log import LogCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


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
            package="test-package", jobname="test-job", wait=False, branch=None, follow=False
        )
        self.mock_package = fixtures.create_mock_project(name="test-package", id=123)
        self.mock_job = fixtures.create_mock_job(
            id=123, status="running", name="test-job"
        )
        self.pkg_handler.get_job_by_name.return_value = self.mock_job
        self.pkg_handler.get_job_by_name_from_mr.return_value = None  # Force fallback to get_job_by_name

        self.pkg_handler.get_package.return_value = self.mock_package
        
        self.pkg_handler.extract_log_from_job_mr.return_value = None
        self.pkg_handler.extract_log_from_job.return_value = "test log content"

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

    def test_normalize_gitlab_log(self):
        """Test normalize_gitlab_log method correctly handles carriage returns."""
        # Test with various types of line endings
        raw_log = "Line 1\rLine 2\r\nLine 3\r\rLine 4"
        normalized_log = self.command.normalize_gitlab_log(raw_log)

        expected_output = "Line 1\nLine 2\nLine 3\n\nLine 4"
        self.assertEqual(normalized_log, expected_output)

    @patch.object(LogCommand, '_show_static_log')
    def test_execute_successful_with_log(self, mock_show_static_log):
        """Test execute method successfully displays log output."""
        result = self.command.execute()

        self.assertEqual(result, 0)
        self.pkg_handler.get_package.assert_called_once_with("test-package")
        self.pkg_handler.get_job_by_name.assert_called_once_with(
            self.mock_package, "test-job"
        )
        mock_show_static_log.assert_called_once_with(self.mock_package)

    @patch.object(LogCommand, '_show_static_log')
    def test_execute_with_empty_log(self, mock_show_static_log):
        """Test execute method with empty log output."""
        result = self.command.execute()

        self.assertEqual(result, 0)
        mock_show_static_log.assert_called_once_with(self.mock_package)

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
        # Setup the mock to return None for both job retrieval methods
        self.pkg_handler.get_job_by_name_from_mr.return_value = None
        self.pkg_handler.get_job_by_name.return_value = None

        result = self.command.execute()

        self.assertEqual(result, 1)
        # Verify appropriate error was logged
        self.mock_logger.error.assert_called_with(
            "Job '%s' not found in merge request or branch pipeline", "test-job"
        )

    def test_show_static_log_extract_failed(self):
        """Test _show_static_log method when extract_log_from_job fails."""
        self.pkg_handler.extract_log_from_job_mr.return_value = None
        self.pkg_handler.extract_log_from_job.return_value = None
        
        self.command._show_static_log(self.mock_package)
        
        self.mock_logger.error.assert_called_with(
            "Failed to extract log from job %s", "test-job"
        )

    def test_execute_job_waiting_failed(self):
        """Test execute method when waiting for job fails."""
        self.args.wait = True
        self.command = LogCommand(self.pkg_handler, self.args)
        
        # Mock _wait_for_job_start to return None
        with patch.object(self.command, "_wait_for_job_start", return_value=None):
            result = self.command.execute()

        self.assertEqual(result, 1)
        # Verify the logger was called with correct error message
        self.mock_logger.error.assert_called_once_with(
            "Job %s did not start.", "test-job"
        )
