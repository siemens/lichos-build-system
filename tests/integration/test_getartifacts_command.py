"""
Integration tests for the 'getartifacts' command.
"""

import os
import shutil
import tempfile
from unittest.mock import patch, Mock

from lichoscli.commands.getartifacts import GetartifactsCommand
from tests.fixtures import TestConstants, create_mock_args


class TestGetartifactsCommandIntegration:
    """Integration tests for the 'getartifacts' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.mock_package = Mock()
        self.mock_package.name = TestConstants.DEFAULT_PROJECT_NAME

        # Create mock pipeline and jobs
        self.mock_pipeline = Mock()
        self.mock_job1 = Mock()
        self.mock_job1.name = "build-debian"
        self.mock_job1.artifacts_file = {"filename": "artifacts.zip"}

        self.mock_job2 = Mock()
        self.mock_job2.name = "test"
        self.mock_job2.artifacts_file = {"filename": "test-artifacts.zip"}

        self.mock_jobs = Mock()
        self.mock_jobs.list.return_value = [self.mock_job1, self.mock_job2]
        self.mock_pipeline.jobs = self.mock_jobs

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.get_package.return_value = self.mock_package
        self.mock_pkg_handler.get_latest_pipeline.return_value = self.mock_pipeline

        # For successful test case, setup a temp directory
        self.temp_dir = tempfile.mkdtemp()
        self.mock_pkg_handler.get_job_artifacts.return_value = self.temp_dir

        self.patches.append(self.pkg_handler_patcher)

        # Mock BuildUtils.get_package_name
        self.get_package_name_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name",
            return_value=TestConstants.DEFAULT_PROJECT_NAME,
        )
        self.get_package_name_patcher.start()
        self.patches.append(self.get_package_name_patcher)

        # Mock os and shutil functions
        self.os_makedirs_patcher = patch("os.makedirs")
        self.mock_os_makedirs = self.os_makedirs_patcher.start()
        self.patches.append(self.os_makedirs_patcher)

        self.os_path_exists_patcher = patch("os.path.exists")
        self.mock_os_path_exists = self.os_path_exists_patcher.start()
        # Assume directories exist by default
        self.mock_os_path_exists.return_value = True
        self.patches.append(self.os_path_exists_patcher)

        self.shutil_rmtree_patcher = patch("shutil.rmtree")
        self.mock_shutil_rmtree = self.shutil_rmtree_patcher.start()
        self.patches.append(self.shutil_rmtree_patcher)

        self.shutil_move_patcher = patch("shutil.move")
        self.mock_shutil_move = self.shutil_move_patcher.start()
        self.patches.append(self.shutil_move_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

        # Clean up temp directory if it exists
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_getartifacts_with_job_name_success(self):
        """Test getting artifacts with a specific job name"""
        # Create arguments for the getartifacts command
        job_name = "build-debian"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME,
            job_name=job_name,
            branch=TestConstants.DEFAULT_BRANCH,
        )

        # Execute the command
        getartifacts_cmd = GetartifactsCommand(self.mock_pkg_handler, args)

        # Mock the instance methods that deal with directories
        with patch.object(getartifacts_cmd, "clear_artifacts_directory") as mock_clear:
            with patch.object(
                getartifacts_cmd, "move_artifacts_to_directory"
            ) as mock_move:
                result = getartifacts_cmd.execute()

                # Verify package was retrieved
                self.mock_pkg_handler.get_package.assert_called_once_with(
                    TestConstants.DEFAULT_PROJECT_NAME
                )

                # Verify artifacts directory was cleared
                mock_clear.assert_called_once_with("artifacts")

                # Verify artifacts were requested with correct parameters
                self.mock_pkg_handler.get_job_artifacts.assert_called_once_with(
                    branch_name=TestConstants.DEFAULT_BRANCH,
                    job_name=job_name,
                    package=self.mock_package,
                )

                # Verify artifacts were moved to the destination directory
                mock_move.assert_called_once_with("artifacts", self.temp_dir)

                # Check return code
                assert result == 0

    def test_getartifacts_with_job_name_failure(self):
        """Test getting artifacts when job artifacts can't be retrieved"""
        # Configure mock to indicate failure retrieving artifacts
        self.mock_pkg_handler.get_job_artifacts.return_value = None

        # Create arguments for the getartifacts command
        job_name = "build-debian"
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME,
            job_name=job_name,
            branch=TestConstants.DEFAULT_BRANCH,
        )

        # Execute the command
        getartifacts_cmd = GetartifactsCommand(self.mock_pkg_handler, args)

        # Mock the instance method for clarity
        with patch.object(getartifacts_cmd, "clear_artifacts_directory"):
            with patch.object(
                getartifacts_cmd, "generate_links_from_jobs"
            ) as mock_generate_links:
                getartifacts_cmd.execute()

                # Verify package was retrieved
                self.mock_pkg_handler.get_package.assert_called_once_with(
                    TestConstants.DEFAULT_PROJECT_NAME
                )

                # Verify latest pipeline was fetched as fallback
                self.mock_pkg_handler.get_latest_pipeline.assert_called_once_with(
                    TestConstants.DEFAULT_PROJECT_NAME, TestConstants.DEFAULT_BRANCH
                )

                # Verify links were generated from jobs
                mock_generate_links.assert_called_once_with(
                    [self.mock_job1, self.mock_job2]
                )

                # Return code depends on implementation details not visible in the file excerpt

    def test_getartifacts_no_job_name(self):
        """Test getting artifacts without specifying a job name"""
        # Create arguments for the getartifacts command without job_name
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME,
            job_name=None,
            branch=TestConstants.DEFAULT_BRANCH,
        )

        # Execute the command
        getartifacts_cmd = GetartifactsCommand(self.mock_pkg_handler, args)

        # Mock the instance method
        with patch.object(
            getartifacts_cmd,
            "generate_links_from_jobs",
            return_value=["link1", "link2"],
        ) as mock_generate_links:
            getartifacts_cmd.execute()

            # Verify package was retrieved
            self.mock_pkg_handler.get_package.assert_called_once_with(
                TestConstants.DEFAULT_PROJECT_NAME
            )

            # Verify job artifacts were not requested
            self.mock_pkg_handler.get_job_artifacts.assert_not_called()

            # Verify latest pipeline was fetched
            self.mock_pkg_handler.get_latest_pipeline.assert_called_once_with(
                TestConstants.DEFAULT_PROJECT_NAME, TestConstants.DEFAULT_BRANCH
            )

            # Verify jobs were listed
            assert self.mock_jobs.list.called

            # Verify links were generated from jobs
            mock_generate_links.assert_called_once_with(
                [self.mock_job1, self.mock_job2]
            )

            # Return code depends on implementation details not visible in the file excerpt

    def test_getartifacts_no_pipeline(self):
        """Test getting artifacts when no pipeline exists"""
        # Configure mock to indicate no pipeline exists
        self.mock_pkg_handler.get_latest_pipeline.return_value = None

        # Create arguments for the getartifacts command without job_name
        args = create_mock_args(
            package=TestConstants.DEFAULT_PROJECT_NAME,
            job_name=None,
            branch=TestConstants.DEFAULT_BRANCH,
        )

        # Execute the command
        getartifacts_cmd = GetartifactsCommand(self.mock_pkg_handler, args)
        result = getartifacts_cmd.execute()

        # Verify package was retrieved
        self.mock_pkg_handler.get_package.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME
        )

        # Verify latest pipeline was requested
        self.mock_pkg_handler.get_latest_pipeline.assert_called_once_with(
            TestConstants.DEFAULT_PROJECT_NAME, TestConstants.DEFAULT_BRANCH
        )

        # Check return code (failure)
        assert result == 1
