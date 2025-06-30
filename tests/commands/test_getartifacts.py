import unittest
from unittest.mock import Mock, patch, MagicMock
from lichoscli.commands.getartifacts import GetartifactsCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestGetartifactsCommand(unittest.TestCase):
    def setUp(self):
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}
        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.job_name = None
        self.args.branch = "main"

    def test_command_initialization_sets_correct_attributes(self):
        command = GetartifactsCommand(self.pkg_handler, self.args)
        self.assertEqual(command.package_name, "test-package")
        self.assertEqual(command.job_name, None)
        self.assertEqual(command.branch, "main")

    @patch("lichoscli.commands.getartifacts.logger")
    def test_execute_no_pipeline_found(self, mock_logger):
        command = GetartifactsCommand(self.pkg_handler, self.args)
        self.pkg_handler.get_package.return_value = Mock()
        self.pkg_handler.get_latest_pipeline.return_value = None
        result = command.execute()
        mock_logger.warning.assert_called_with(
            "No pipeline found for package %s", "test-package"
        )
        self.assertEqual(result, 1)

    @patch("lichoscli.commands.getartifacts.print")
    def test_execute_with_links(self, mock_print):
        command = GetartifactsCommand(self.pkg_handler, self.args)
        self.pkg_handler.get_package.return_value = Mock()
        mock_pipeline = Mock()
        mock_job1 = Mock()
        mock_job1.name = "build-job"
        mock_job1.web_url = "http://example.com/build"
        mock_job2 = Mock()
        mock_job2.name = "test-job"
        mock_job2.web_url = "http://example.com/test"
        mock_pipeline.jobs.list.return_value = [mock_job1, mock_job2]
        self.pkg_handler.get_latest_pipeline.return_value = mock_pipeline
        result = command.execute()
        mock_print.assert_any_call("Artifacts links:")
        mock_print.assert_any_call(
            "build-job: http://example.com/build/artifacts/browse"
        )
        self.assertEqual(result, 0)

    @patch(
        "lichoscli.commands.getartifacts.GetartifactsCommand.move_artifacts_to_directory"
    )
    @patch(
        "lichoscli.commands.getartifacts.GetartifactsCommand.clear_artifacts_directory"
    )
    def test_execute_with_job_name_and_tempdir(self, mock_clear, mock_move):
        self.args.job_name = "build-job"
        command = GetartifactsCommand(self.pkg_handler, self.args)
        self.pkg_handler.get_package.return_value = Mock()
        tempdir = MagicMock()
        self.pkg_handler.get_job_artifacts.return_value = tempdir
        result = command.execute()
        mock_clear.assert_called_once()
        mock_move.assert_called_once_with("artifacts", tempdir)
        self.assertEqual(result, 0)

    @patch(
        "lichoscli.commands.getartifacts.GetartifactsCommand.clear_artifacts_directory"
    )
    def test_execute_with_job_name_and_no_tempdir(self, mock_clear):
        self.args.job_name = "build-job"
        command = GetartifactsCommand(self.pkg_handler, self.args)
        self.pkg_handler.get_package.return_value = Mock()
        self.pkg_handler.get_job_artifacts.return_value = None
        self.pkg_handler.get_latest_pipeline.return_value = None
        result = command.execute()
        mock_clear.assert_called_once()
        self.assertEqual(result, 1)
