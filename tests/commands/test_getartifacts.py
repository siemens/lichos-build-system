# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import MagicMock, Mock, patch

from lichoscli.commands.getartifacts import GetartifactsCommand


class TestGetartifactsCommand:

    def test_command_initialization_sets_correct_attributes(self, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = None
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)
        assert command.package_name == "test-package"
        assert command.job_name is None
        assert command.branch == "main"

    @patch("lichoscli.commands.getartifacts.logger")
    def test_execute_no_pipeline_found(self, mock_logger, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = None
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = None
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package

        result = command.execute()
        mock_logger.warning.assert_called_with("No pipeline found for package %s", "test-package")
        assert result == 1

    @patch("lichoscli.commands.base.Console")
    def test_execute_with_links(self, mock_console_class, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = None
        args.branch = "main"

        mock_console = Mock()
        mock_console_class.return_value = mock_console

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipeline = Mock()
        mock_job1 = Mock()
        mock_job1.name = "build-job"
        mock_job1.web_url = "http://example.com/build"
        mock_job2 = Mock()
        mock_job2.name = "test-job"
        mock_job2.web_url = "http://example.com/test"

        mock_jobs = Mock()
        mock_jobs.list.return_value = [mock_job1, mock_job2]
        mock_pipeline.jobs = mock_jobs

        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = mock_pipeline
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package

        result = command.execute()
        mock_console.print.assert_any_call("[bold]Artifacts links:[/bold]")
        mock_console.print.assert_any_call("  build-job: http://example.com/build/artifacts/browse")
        assert result == 0

    @patch("lichoscli.commands.getartifacts.GetartifactsCommand.move_artifacts_to_directory")
    @patch("lichoscli.commands.getartifacts.GetartifactsCommand.clear_artifacts_directory")
    def test_execute_with_job_name_and_tempdir(self, mock_clear, mock_move, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = "build-job"
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipeline = Mock()
        mock_job = Mock()
        mock_job.name = "build-job"

        tempdir = MagicMock()
        tempdir.name = "/tmp/test"
        mock_artifacts = Mock()
        mock_artifacts.download_as_directory.return_value = tempdir
        mock_job.artifacts = mock_artifacts

        mock_jobs = Mock()
        mock_jobs.get_by_name.return_value = mock_job
        mock_pipeline.jobs = mock_jobs

        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = mock_pipeline
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package

        with patch("lichoscli.commands.getartifacts.ProgressUtils.execute_with_progress") as mock_progress:
            mock_progress.return_value = tempdir
            result = command.execute()

        mock_clear.assert_called_once()
        mock_move.assert_called_once_with("artifacts", tempdir)
        assert result == 0

    @patch("lichoscli.commands.getartifacts.GetartifactsCommand.clear_artifacts_directory")
    def test_execute_with_job_name_and_no_tempdir(self, mock_clear, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = "build-job"
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = None
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package

        result = command.execute()
        mock_clear.assert_called_once()
        assert result == 1
