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
        mock_logger.error.assert_called_with("No pipeline found for branch %s", "main")
        assert result == 1

    def test_execute_no_job_user_selects_single(self, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = None
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipeline = Mock()
        mock_job1 = Mock()
        mock_job1.name = "build-job"
        mock_job1.status = "success"
        mock_job2 = Mock()
        mock_job2.name = "test-job"
        mock_job2.status = "failed"

        mock_jobs = Mock()
        mock_jobs.list.return_value = [mock_job1, mock_job2]
        mock_pipeline.jobs = mock_jobs

        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = mock_pipeline
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package
        mock_di_container.user_interface.prompts.select_many.return_value = ["build-job"]

        with patch.object(command, "_download_specific_job_artifacts", return_value=0) as mock_download:
            result = command.execute()

        mock_di_container.user_interface.prompts.select_many.assert_called_once()
        mock_download.assert_called_once_with(mock_package, "artifacts", "build-job")
        assert result == 0

    def test_execute_no_job_user_selects_multiple(self, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = None
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipeline = Mock()
        mock_job1 = Mock()
        mock_job1.name = "build-job"
        mock_job1.status = "success"
        mock_job2 = Mock()
        mock_job2.name = "test-job"
        mock_job2.status = "success"

        mock_jobs = Mock()
        mock_jobs.list.return_value = [mock_job1, mock_job2]
        mock_pipeline.jobs = mock_jobs

        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = mock_pipeline
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package
        mock_di_container.user_interface.prompts.select_many.return_value = ["build-job", "test-job"]

        with patch.object(command, "_download_specific_job_artifacts", return_value=0) as mock_download:
            result = command.execute()

        mock_di_container.user_interface.prompts.select_many.assert_called_once()
        assert mock_download.call_count == 2
        mock_download.assert_any_call(mock_package, "artifacts", "build-job")
        mock_download.assert_any_call(mock_package, "artifacts", "test-job")
        assert result == 0

    def test_execute_no_job_user_cancels(self, mock_di_container, mock_args):
        args = mock_args()
        args.package = "test-package"
        args.job = None
        args.branch = "main"

        command = GetartifactsCommand(mock_di_container, args)

        mock_package = Mock()
        mock_pipeline = Mock()
        mock_job = Mock()
        mock_job.name = "build-job"
        mock_job.status = "success"

        mock_jobs = Mock()
        mock_jobs.list.return_value = [mock_job]
        mock_pipeline.jobs = mock_jobs

        mock_pipelines = Mock()
        mock_pipelines.get_latest.return_value = mock_pipeline
        mock_package.pipelines = mock_pipelines

        mock_di_container.package_service.get_package.return_value = mock_package
        mock_di_container.user_interface.prompts.select_many.return_value = None

        result = command.execute()

        mock_di_container.user_interface.prompts.select_many.assert_called_once()
        assert result == 0

    @patch("lichoscli.commands.getartifacts.GetartifactsCommand.move_artifacts_to_directory")
    def test_execute_with_job_name_and_tempdir(self, mock_move, mock_di_container, mock_args):
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

        mock_move.assert_called_once_with("artifacts", tempdir)
        assert result == 0

    def test_execute_with_job_name_and_no_tempdir(self, mock_di_container, mock_args):
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
        assert result == 1
