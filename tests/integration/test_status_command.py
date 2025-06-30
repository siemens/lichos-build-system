"""
Integration tests for the 'status' command.
"""

import io
from unittest.mock import patch, Mock

from lichoscli.commands.status import StatusCommand
from tests.fixtures import TestConstants, create_mock_args


class TestStatusCommandIntegration:
    """Integration tests for the 'status' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data and packages
        self.mock_packages = []
        for idx, pkg_name in enumerate(TestConstants.SAMPLE_PROJECTS):
            mock_pkg = Mock()
            mock_pkg.name = pkg_name
            mock_pkg.ci_config_path = ".lichos-ci.yml"
            mock_pkg.builds_access_level = "enabled" if idx % 2 == 0 else "disabled"
            mock_pkg.default_branch = "main"
            self.mock_packages.append(mock_pkg)

        # Set up pipelines
        self.mock_pipelines = {}
        for idx, pkg_name in enumerate(TestConstants.SAMPLE_PROJECTS):
            mock_pipeline = Mock()
            mock_pipeline.sha = f"abc{idx}123"
            mock_pipeline.ref = "main"
            mock_pipeline.status = "success" if idx % 2 == 0 else "failed"
            mock_pipeline.source = "push"
            mock_pipeline.updated_at = f"2023-01-0{idx + 1}T12:00:00"
            mock_pipeline.web_url = f"https://gitlab.com/pipeline/{idx + 100}"

            # Add user for some pipelines
            if idx % 2 == 0:
                mock_user = Mock()
                mock_user.username = f"user{idx}"
                mock_pipeline.user = mock_user

            # Add jobs
            mock_job1 = Mock()
            mock_job1.id = idx * 10 + 1
            mock_job1.name = "build"
            mock_job1.stage = "build"
            mock_job1.status = "success" if idx % 2 == 0 else "failed"
            mock_job1.started_at = f"2023-01-0{idx + 1}T12:00:00"
            mock_job1.finished_at = f"2023-01-0{idx + 1}T12:05:00"

            mock_job2 = Mock()
            mock_job2.id = idx * 10 + 2
            mock_job2.name = "test"
            mock_job2.stage = "test"
            mock_job2.status = "success" if idx % 2 == 0 else "running"
            mock_job2.started_at = f"2023-01-0{idx + 1}T12:05:00"
            mock_job2.finished_at = (
                None if idx % 2 == 1 else f"2023-01-0{idx + 1}T12:10:00"
            )

            mock_pipeline.jobs = Mock()
            mock_pipeline.jobs.list = Mock(return_value=[mock_job1, mock_job2])

            self.mock_pipelines[pkg_name] = mock_pipeline

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_all_packages.return_value = self.mock_packages
        self.mock_pkg_handler.get_latest_pipeline.side_effect = lambda pkg_name, brancha = None: (
            self.mock_pipelines.get(pkg_name)
            if pkg_name in self.mock_pipelines
            else None
        )
        self.mock_pkg_handler.get_all_pipelines_status.return_value = self.mock_pipelines
        self.patches.append(self.pkg_handler_patcher)

        # Mock TimeUtils format_time_range
        self.time_utils_patcher = patch(
            "lichoscli.utils.TimeUtils.format_time_range", return_value="5 minutes"
        )
        self.time_utils_patcher.start()
        self.patches.append(self.time_utils_patcher)

        # Mock CIConfigUtils get_type_from_ci_path
        self.ci_utils_patcher = patch(
            "lichoscli.utils.CIConfigUtils.get_type_from_ci_path", return_value="gbp"
        )
        self.ci_utils_patcher.start()
        self.patches.append(self.ci_utils_patcher)

        # Mock GitUtils methods
        self.get_group_patcher = patch(
            "lichoscli.utils.GitUtils.get_group",
            return_value=TestConstants.DEFAULT_GROUP_PATH,
        )
        self.get_group_patcher.start()
        self.patches.append(self.get_group_patcher)

        self.get_branch_patcher = patch(
            "lichoscli.utils.GitUtils.get_branch",
            return_value=TestConstants.DEFAULT_BRANCH,
        )
        self.get_branch_patcher.start()
        self.patches.append(self.get_branch_patcher)

        # Mock git.Repo
        self.git_repo_patcher = patch("git.Repo")
        self.mock_repo_class = self.git_repo_patcher.start()
        self.mock_repo = self.mock_repo_class.return_value
        self.mock_head = Mock()
        self.mock_ref = Mock()
        self.mock_ref.__str__ = lambda x: TestConstants.DEFAULT_BRANCH
        self.mock_head.reference = self.mock_ref
        self.mock_repo.head = self.mock_head
        self.patches.append(self.git_repo_patcher)


    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_status_all_packages(self):
        """Test that status command without specific package shows all packages status"""
        # Create a mock of sys.stdout to capture output
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Create and execute the status command directly
            args = create_mock_args()
            args.package = None
            command = StatusCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = mock_stdout.getvalue()

            # Verify command executed successfully
            assert result == 0

            # Verify output contains expected headers
            assert "Name" in output
            assert "Type" in output
            assert "Enabled" in output
            assert "Status" in output
            assert "Pipeline" in output

            # Verify each package appears in output
            for pkg_name in TestConstants.SAMPLE_PROJECTS:
                assert pkg_name in output

            # Check that status values appear
            assert "success" in output
            assert "failed" in output

    def test_status_specific_package(self):
        """Test that status command with specific package shows detailed information"""
        # Create a mock of sys.stdout to capture output
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Create and execute the status command directly
            args = create_mock_args()
            test_package = TestConstants.SAMPLE_PROJECTS[0]
            args.package = test_package
            command = StatusCommand(self.mock_pkg_handler, args)
            result = command.execute()

            # Get captured output
            output = mock_stdout.getvalue()

            # Verify command executed successfully
            assert result == 0

            # Verify output contains expected headers and information
            assert "Setting" in output
            assert "Value" in output
            assert "sha" in output
            assert "ref" in output
            assert "status" in output
            assert "Pipeline Jobs" in output
            assert "build" in output
            assert "test" in output
            assert "Id" in output
            assert "Stage" in output
            assert "Started" in output

    def test_status_package_not_found(self):
        """Test status command behavior when package is not found"""
        # Set up the mock to return None for nonexistent package
        self.mock_pkg_handler.get_latest_pipeline.return_value = None

        # Create logger mock to capture warnings
        with patch("lichoscli.commands.status.logger") as mock_logger:
            # Create and execute the status command with non-existent package
            args = create_mock_args()
            args.package = "nonexistent-package"
            command = StatusCommand(self.mock_pkg_handler, args)
            result = command.print_package_status()

            # Verify logger was called with error message
            mock_logger.error.assert_called_once_with(
                "No pipeline found for package %s", "nonexistent-package"
            )

            # Verify function returns None when pipeline not found
            assert result is None

    def test_status_with_dump_flag(self):
        """Test status command with dump flag enabled"""
        # Create a mock of sys.stdout to capture output
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Set up the dump flag
            args = create_mock_args()
            test_package = TestConstants.SAMPLE_PROJECTS[0]
            args.package = test_package
            args.dump = True

            # Mock json.dumps to return a predictable string
            with patch(
                "lichoscli.commands.status.json.dumps",
                return_value='{"mocked": "json"}',
            ):
                command = StatusCommand(self.mock_pkg_handler, args)
                command.print_package_status()

                # Get captured output
                output = mock_stdout.getvalue()

                # Verify json output was printed
                assert '{"mocked": "json"}' in output
