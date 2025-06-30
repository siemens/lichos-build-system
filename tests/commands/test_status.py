import unittest
from unittest.mock import Mock, patch, call
from lichoscli.commands.status import StatusCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestStatusCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""

        # Reset command registry for test isolation
        CommandRegister._commands = {}  # noqa
        CommandRegister._parser_hooks = {}  # noqa

        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.dump = False

        self.command = StatusCommand(self.pkg_handler, self.args)

        # Mock git.Repo
        self.git_repo_patcher = patch("git.Repo")
        self.mock_repo_class = self.git_repo_patcher.start()
        self.mock_repo = self.mock_repo_class.return_value
        self.mock_head = Mock()
        self.mock_ref = Mock()
        self.mock_ref.__str__ = lambda x: TestConstants.DEFAULT_BRANCH
        self.mock_head.reference = self.mock_ref
        self.mock_repo.head = self.mock_head

    def test_command_initialization_sets_correct_attributes(self):
        """Test that command initialization sets correct attributes."""
        self.assertEqual(self.command.pkg_group_handler, self.pkg_handler)
        self.assertEqual(self.command.package_name, "test-package")
        self.assertEqual(self.command.dump, False)

    def test_execute_with_package_name_calls_print_package_status(self):
        """Test that execute calls print_package_status when package name is provided."""
        with patch.object(
            self.command, "print_package_status", return_value=0
        ) as mock_print_package:
            result = self.command.execute()

            mock_print_package.assert_called_once()
            self.assertEqual(result, 0)

    def test_execute_without_package_name_calls_print_all_status(self):
        """Test that execute calls print_all_status when no package name is provided."""
        self.args.package = None
        command = StatusCommand(self.pkg_handler, self.args)

        with patch.object(
            command, "print_all_status", return_value=0
        ) as mock_print_all:
            result = command.execute()

            mock_print_all.assert_called_once()
            self.assertEqual(result, 0)

    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.tabulate")
    def test_print_all_status_with_packages_and_pipelines(
        self, mock_tabulate, mock_print
    ):
        """Test print_all_status with packages that have pipelines."""

        mock_package1 = fixtures.create_mock_project(
            name="package1", ci_config_path="gbp.yml@test-group/pkg/00ci"
        )
        mock_package2 = fixtures.create_mock_project(
            name="package2",
            ci_config_path="image.yml@test-group/pkg/00ci",
            builds_access_level="disabled",
        )

        mock_pipeline1 = Mock()
        mock_pipeline1.status = "success"
        mock_pipeline1.updated_at = "2023-01-01T12:00:00"

        mock_pipeline2 = Mock()
        mock_pipeline2.status = "failed"
        mock_pipeline2.updated_at = "2023-01-02T15:30:00"

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package1, mock_package2])
        self.pkg_handler.get_all_pipelines_status = Mock()
        self.pkg_handler.get_all_pipelines_status.side_effect = lambda max_workers, branch = None: {
            "package1": mock_pipeline1,
            "package2": mock_pipeline2,
        }
        mock_tabulate.return_value = "formatted_status_table"

        result = self.command.print_all_status()

        self.assertEqual(result, 0)

        self.pkg_handler.get_all_packages.assert_called_once()

        expected_table = [
            ["Name", "Type", "Enabled", "Status", "Pipeline"],
            ["package1", "gbp", "enabled", "success", "2023-01-01 12:00:00"],
            ["package2", "image", "disabled", "failed", "2023-01-02 15:30:00"],
        ]
        mock_tabulate.assert_called_once_with(expected_table, headers="firstrow")
        mock_print.assert_called_once_with("formatted_status_table")

    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.tabulate")
    def test_print_all_status_with_packages_without_pipelines(self, mock_tabulate, _):
        """Test print_all_status with packages that have no pipelines."""
        mock_package = fixtures.create_mock_project(
            name="package1", ci_config_path="gbp.yml@test-group/pkg/00ci"
        )

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package])
        self.pkg_handler.get_all_pipelines_status = Mock(return_value={"package1": None})

        mock_tabulate.return_value = "formatted_status_table"

        result = self.command.print_all_status()

        self.assertEqual(result, 0)

        expected_table = [
            ["Name", "Type", "Enabled", "Status", "Pipeline"],
            ["package1", "gbp", "enabled", "-", "-"],
        ]
        mock_tabulate.assert_called_once_with(expected_table, headers="firstrow")

    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.tabulate")
    def test_print_all_status_with_invalid_date_format(self, mock_tabulate, _):
        """Test print_all_status handles invalid date formats gracefully."""
        mock_package = fixtures.create_mock_project(
                name="package1", ci_config_path="gbp.yml@test-group/pkg/00ci"
        )

        mock_pipeline = Mock()
        mock_pipeline.status = "success"
        mock_pipeline.updated_at = "invalid-date-format"

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package])
        self.pkg_handler.get_all_pipelines_status = Mock(return_value={"package1": mock_pipeline})
        mock_tabulate.return_value = "formatted_status_table"

        result = self.command.print_all_status()

        self.assertEqual(result, 0)

        expected_table = [
            ["Name", "Type", "Enabled", "Status", "Pipeline"],
            [
                "package1",
                "gbp",
                "enabled",
                "success",
                "(Invalid date: invalid-date-format)",
            ],
        ]
        mock_tabulate.assert_called_once_with(expected_table, headers="firstrow")

    @patch("lichoscli.commands.status.logger")
    def test_print_package_status_no_pipeline_found(self, mock_logger):
        """Test print_package_status when no pipeline is found."""
        self.pkg_handler.get_latest_pipeline = Mock(return_value=None)

        result = self.command.print_package_status()

        self.pkg_handler.get_latest_pipeline.assert_called_once_with("test-package", "main")

        mock_logger.error.assert_called_once_with(
            "No pipeline found for package %s", "test-package"
        )

        self.assertIsNone(result)

    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.json.dumps")
    def test_print_package_status_with_dump_flag(self, mock_json_dumps, mock_print):
        """Test print_package_status with dump flag enabled."""
        self.args.dump = True
        command = StatusCommand(self.pkg_handler, self.args)

        mock_pipeline = Mock()
        self.pkg_handler.get_latest_pipeline = Mock(return_value=mock_pipeline)
        mock_json_dumps.return_value = '{"pipeline": "data"}'

        result = command.print_package_status()

        self.pkg_handler.get_latest_pipeline.assert_called_once_with("test-package", "main")

        mock_json_dumps.assert_called_once_with(mock_pipeline, indent=2)

        mock_print.assert_called_once_with('{"pipeline": "data"}')

        self.assertIsNone(result)

    @patch("lichoscli.commands.status.utils.TimeUtils.format_time_range")
    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.tabulate")
    def test_print_package_status_with_pipeline_and_jobs(
        self, mock_tabulate, mock_print, mock_format_time
    ):
        """Test print_package_status with pipeline and jobs."""

        mock_pipeline = Mock()
        mock_pipeline.sha = "abc123"
        mock_pipeline.ref = "main"
        mock_pipeline.status = "success"
        mock_pipeline.source = "push"
        mock_pipeline.web_url = "https://gitlab.com/pipeline/123"

        mock_user = Mock()
        mock_user.username = "testuser"
        mock_pipeline.user = mock_user

        mock_job1 = Mock()
        mock_job1.id = 1
        mock_job1.name = "build"
        mock_job1.stage = "build"
        mock_job1.status = "success"
        mock_job1.started_at = "2023-01-01T12:00:00"
        mock_job1.finished_at = "2023-01-01T12:05:00"

        mock_job2 = Mock()
        mock_job2.id = 2
        mock_job2.name = "test"
        mock_job2.stage = "test"
        mock_job2.status = "success"
        mock_job2.started_at = "2023-01-01T12:05:00"
        mock_job2.finished_at = "2023-01-01T12:10:00"

        mock_pipeline.jobs.list.return_value = [mock_job1, mock_job2]

        self.pkg_handler.get_latest_pipeline = Mock(return_value=mock_pipeline)
        mock_tabulate.side_effect = ["pipeline_table_output", "jobs_table_output"]
        mock_format_time.side_effect = ["5 minutes", "5 minutes"]

        result = self.command.print_package_status()

        self.assertEqual(result, 0)

        self.pkg_handler.get_latest_pipeline.assert_called_once_with("test-package", "main")

        self.assertEqual(mock_tabulate.call_count, 2)

        expected_pipeline_headers = [
            ["Setting", "Value"],
            ["sha", "abc123"],
            ["ref", "main"],
            ["status", "success"],
            ["source", "push"],
            ["web_url", "https://gitlab.com/pipeline/123"],
            ["user", "testuser"],
        ]
        mock_tabulate.assert_any_call(expected_pipeline_headers, headers="firstrow")

        expected_job_headers = ["Id", "Name", "Stage", "Status", "Started"]
        expected_job_rows = [
            [1, "build", "build", "success", "5 minutes"],
            [2, "test", "test", "success", "5 minutes"],
        ]
        mock_tabulate.assert_any_call(expected_job_rows, headers=expected_job_headers)

        expected_print_calls = [
            call("pipeline_table_output"),
            call("\nPipeline Jobs:\n"),
            call("jobs_table_output"),
        ]
        mock_print.assert_has_calls(expected_print_calls)

    @patch("lichoscli.commands.status.utils.TimeUtils.format_time_range")
    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.tabulate")
    def test_print_package_status_without_user(self, mock_tabulate, _, __):
        """Test print_package_status with pipeline that has no user."""

        mock_pipeline = Mock()
        mock_pipeline.sha = "abc123"
        mock_pipeline.ref = "main"
        mock_pipeline.status = "success"
        mock_pipeline.source = "push"
        mock_pipeline.web_url = "https://gitlab.com/pipeline/123"

        del mock_pipeline.user

        mock_pipeline.jobs.list.return_value = []

        self.pkg_handler.get_latest_pipeline = Mock(return_value=mock_pipeline)
        mock_tabulate.side_effect = ["pipeline_table_output", "jobs_table_output"]

        result = self.command.print_package_status()

        self.assertEqual(result, 0)

        expected_pipeline_headers = [
            ["Setting", "Value"],
            ["sha", "abc123"],
            ["ref", "main"],
            ["status", "success"],
            ["source", "push"],
            ["web_url", "https://gitlab.com/pipeline/123"],
        ]
        mock_tabulate.assert_any_call(expected_pipeline_headers, headers="firstrow")

    @patch("lichoscli.commands.status.print")
    @patch("lichoscli.commands.status.tabulate")
    def test_execute_with_empty_package_name(self, mock_tabulate, _):
        """Test execute behavior when package name is empty string."""
        self.args.package = ""
        command = StatusCommand(self.pkg_handler, self.args)

        mock_package = fixtures.create_mock_project(
            name="package1", ci_config_path="gbp.yml@test-group/pkg/00ci"
        )

        mock_pipeline = Mock()
        mock_pipeline.status = "success"
        mock_pipeline.updated_at = "invalid-date-format"

        self.pkg_handler.get_all_packages = Mock(return_value=[mock_package])
        self.pkg_handler.get_all_pipelines_status = Mock(return_value={"package1": None})
        mock_tabulate.return_value = "formatted_status_table"

        with patch.object(
            command, "print_all_status", return_value=0
        ) as mock_print_package:
            result = command.execute()

            mock_print_package.assert_called_once()
            self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
