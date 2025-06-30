import pytest
from unittest.mock import Mock, patch, mock_open
from lichoscli.pkg import PkgGroupHandler
from tests import fixtures


class TestPkgGroupHandler:

    @pytest.fixture
    def mock_gitlab(self):
        return fixtures.create_mock_gitlab()

    @pytest.fixture
    def pkg_handler(self, mock_gitlab):
        return fixtures.create_mock_pkg_handler("test-group/pkg", mock_gitlab)

    def test_init(self, mock_gitlab):
        """Test PkgGroupHandler initialization"""
        handler = PkgGroupHandler("test-group/pkg", mock_gitlab)
        assert handler.group_rpath == "test-group/pkg"
        assert handler.gitlab == mock_gitlab
        assert handler._packages_cache == {}
        assert handler._all_packages_cache is None

    def test_get_all_packages(self, pkg_handler):
        """Test getting all packages"""
        packages = pkg_handler.get_all_packages()
        assert len(packages) == 4
        assert packages[0].name == "package1"
        assert packages[3].name == "package4"
        assert packages[3].namespace["path"] == "subgroup"

        assert pkg_handler._all_packages_cache is not None
        assert "package1" in pkg_handler._packages_cache

    def test_get_package_with_cache(self, pkg_handler):
        """Test getting a package with caching"""

        package = pkg_handler.get_package("package1")
        assert package.name == "package1"

        cached_package = pkg_handler.get_package("package1")
        assert cached_package == package

    def test_get_package_with_subgroup(self, pkg_handler):
        """Test getting a package from a subgroup"""
        package = pkg_handler.get_package("package4")
        assert package.name == "package4"
        assert package.namespace["path"] == "subgroup"

    def test_get_package_not_found(self, pkg_handler):
        """Test getting a non-existent package"""
        package = pkg_handler.get_package("non-existent-package")
        assert package is None

    def test_update_package(self, pkg_handler):
        """Test updating package settings"""
        updated_pkg = pkg_handler.update_package(
            "package1",
            ci_config_path="new-ci.yml",
            branch="develop",
            access_level="disabled",
        )

        assert updated_pkg.ci_config_path == "new-ci.yml"
        assert updated_pkg.default_branch == "develop"
        assert updated_pkg.builds_access_level == "disabled"

    def test_update_package_not_found(self, pkg_handler):
        """Test updating non-existent package"""
        result = pkg_handler.update_package("non-existent-package")
        assert result is None

    def test_add_package(self, pkg_handler):
        """Test adding a new package"""
        with patch(
            "lichoscli.utils.CIConfigUtils.get_ci_path", return_value=".gitlab-ci.yml"
        ) as mock_get_ci_path:
            assert mock_get_ci_path.called is False
            new_pkg = pkg_handler.add_package(
                "new-package",
                branch="main",
                package_type="standard",
                access_level="enabled",
                subgroup="subgroup",
            )

            assert new_pkg is not None
            assert new_pkg.name == "new-package"
            assert new_pkg.default_branch == "main"
            assert new_pkg.builds_access_level == "enabled"

    def test_get_latest_pipeline(self, pkg_handler):
        """Test getting the latest pipeline"""

        mock_pipeline = fixtures.create_mock_pipeline()
        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = [mock_pipeline]

        pipeline = pkg_handler.get_latest_pipeline("package1")
        assert pipeline.id == mock_pipeline.id
        assert pipeline.status == "success"

    def test_get_latest_pipeline_no_pipelines(self, pkg_handler):
        """Test getting latest pipeline when none exist"""
        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = []

        pipeline = pkg_handler.get_latest_pipeline("package1")
        assert pipeline is None

    def test_refresh_packages(self, pkg_handler):
        """Test refreshing package cache"""

        pkg_handler.get_all_packages()
        assert pkg_handler._all_packages_cache is not None
        assert pkg_handler._packages_cache != {}

        pkg_handler._refresh_packages()
        assert pkg_handler._all_packages_cache is None
        assert pkg_handler._packages_cache == {}

    def test_package_cache_decorator(self, pkg_handler):
        """Test the package_cache decorator functionality"""

        pkg_handler.get_package("package1")
        assert "package1" in pkg_handler._packages_cache

        pkg_handler._packages_cache["package1"] = "modified"

        pkg2 = pkg_handler.get_package("package1")
        assert pkg2 == "modified"

    def test_get_job_by_name(self, pkg_handler):
        """Test finding a job by name in the latest pipeline"""
        # Set up the mocks
        mock_pipeline = fixtures.create_mock_pipeline()
        mock_job = Mock()
        mock_job.name = "build"
        mock_job.id = 101

        # Configure the mock pipeline to return our mock job
        mock_pipeline.jobs.list.return_value = [mock_job]

        # Configure the package to return our mock pipeline
        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = [mock_pipeline]

        # Test getting an existing job
        job = pkg_handler.get_job_by_name(pkg, "build")
        assert job is not None
        assert job.name == "build"
        assert job.id == 101

        # Test getting a non-existent job
        job = pkg_handler.get_job_by_name(pkg, "non-existent-job")
        assert job is None

    def test_get_job_by_name_no_pipeline(self, pkg_handler):
        """Test get_job_by_name when no pipeline exists"""
        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = []

        job = pkg_handler.get_job_by_name(pkg, "build")
        assert job is None

    def test_get_job_by_name_no_jobs(self, pkg_handler):
        """Test get_job_by_name when pipeline has no jobs"""
        mock_pipeline = fixtures.create_mock_pipeline()
        mock_pipeline.jobs.list.return_value = []

        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = [mock_pipeline]

        job = pkg_handler.get_job_by_name(pkg, "build")
        assert job is None

    def test_get_package_variables(self, pkg_handler):
        """Test getting package variables"""
        # Create mock package with variables
        package = Mock()
        package.name = "test-package"
        package.id = 123
        var1 = Mock()
        var1.key = "VAR1"
        var1.value = "value1"
        var2 = Mock()
        var2.key = "VAR2"
        var2.value = "value2"

        package.variables.list.return_value = [var1, var2]

        # Test the instance method
        variables = pkg_handler.get_package_variables(package)

        assert variables is not None
        assert len(variables) == 2
        assert variables["VAR1"] == "value1"
        assert variables["VAR2"] == "value2"

    @patch("tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    @patch("os.path.getsize")
    @patch("os.path.join", return_value="/tmp/artifacts/build-job_main.zip")
    @patch("os.unlink")
    def test_get_job_artifacts_success(
        self, mock_unlink, mock_join, mock_getsize, mock_subprocess, mock_tempdir
    ):
        """Test successful retrieval of job artifacts"""
        # Mock setup
        package = Mock()
        package.default_branch = "main"

        # Configure the mocks
        mock_tempdir_instance = Mock()
        mock_tempdir.return_value = mock_tempdir_instance
        mock_tempdir_instance.name = "/tmp/artifacts"

        # Mock file size check to ensure it doesn't think the file is empty
        mock_getsize.return_value = 1024

        # Mock the download
        package.artifacts.download.return_value = b"mock zip content"

        # Mock file open
        with patch("builtins.open", mock_open()) as mock_file:
            # Prevent actual filesystem access by mocking the result
            result = PkgGroupHandler.get_job_artifacts(package, "main", "build-job")

            # Verify results
            assert result is not None
            assert result == mock_tempdir_instance
            package.artifacts.download.assert_called_once_with(
                job="build-job", ref_name="main"
            )
            mock_file.assert_called_once()
            mock_subprocess.assert_called_once()
            mock_unlink.assert_called_once()

    @patch("tempfile.TemporaryDirectory")
    def test_get_job_artifacts_download_fails(self, mock_tempdir):
        """Test job artifacts download failure"""
        # Mock setup
        package = Mock()
        package.default_branch = "main"
        package.artifacts.download.return_value = None

        # Configure the temp dir mock
        mock_tempdir_instance = Mock()
        mock_tempdir.return_value = mock_tempdir_instance

        # Test with failed download
        result = PkgGroupHandler.get_job_artifacts(package, "main", "build-job")

        # Verify results
        assert result is None
        mock_tempdir_instance.cleanup.assert_called_once()

    @patch("tempfile.TemporaryDirectory")
    @patch("os.path.getsize")
    def test_get_job_artifacts_empty_file(self, mock_getsize, mock_tempdir):
        """Test job artifacts with empty downloaded file"""
        # Mock setup
        package = Mock()
        package.default_branch = "main"
        package.artifacts.download.return_value = b"content"

        # Configure the mocks
        mock_tempdir_instance = Mock()
        mock_tempdir.return_value = mock_tempdir_instance
        mock_tempdir_instance.name = "/tmp/artifacts"

        # Mock file size as empty
        mock_getsize.return_value = 0

        # Test with empty file
        with patch("builtins.open", mock_open()):
            result = PkgGroupHandler.get_job_artifacts(package, "main", "build-job")

            # Verify results
            assert result is None
            mock_tempdir_instance.cleanup.assert_called_once()

    @patch("tempfile.TemporaryDirectory")
    def test_get_job_artifacts_exception(self, mock_tempdir):
        """Test job artifacts with exception during processing"""
        # Mock setup
        package = Mock()
        package.default_branch = "main"

        # Instead of setting side_effect on download, we'll force an exception
        # in the get_artifacts_by_branch and get_artifacts_by_mr methods
        with patch.object(
            PkgGroupHandler,
            "get_artifacts_by_branch",
            side_effect=Exception("Branch download error"),
        ), patch.object(
            PkgGroupHandler,
            "get_artifacts_by_mr",
            side_effect=Exception("MR download error"),
        ):

            # Configure the temp dir mock
            mock_tempdir_instance = Mock()
            mock_tempdir.return_value = mock_tempdir_instance

            result = PkgGroupHandler.get_job_artifacts(package, "main", "build-job")

            # Verify results
            assert result is None
            mock_tempdir_instance.cleanup.assert_called_once()

    def test_trigger_package_build_with_default_branch(self, pkg_handler):
        """Test triggering a package build"""
        # Create mock package and trigger
        package = Mock()
        package.name = "package1"
        package.default_branch = "main"

        # Test trigger build
        result = pkg_handler.trigger_package_build(package)

        # Verify results
        assert result == 0
        package.pipelines.create.assert_called_once_with({'ref': 'main'})

    def test_trigger_package_build_with_custom_branch(self, pkg_handler):
        """Test triggering a package build"""
        # Create mock package and trigger
        package = Mock()
        package.name = "package1"
        package.default_branch = "main"

        # Test trigger build
        result = pkg_handler.trigger_package_build(package, 'test-branch')

        # Verify results
        assert result == 0
        package.pipelines.create.assert_called_once_with({'ref': 'test-branch'})

    def test_get_artifacts_by_branch(self):
        """Test getting artifacts directly by branch name"""
        # Mock setup
        package = Mock()
        package.artifacts.download.return_value = b"mock zip content"

        # Test successful download
        result = PkgGroupHandler.get_artifacts_by_branch(package, "main", "build-job")
        assert result == b"mock zip content"
        package.artifacts.download.assert_called_once_with(
            job="build-job", ref_name="main"
        )

        # Test failed download
        package.artifacts.download.side_effect = Exception("Download failed")
        result = PkgGroupHandler.get_artifacts_by_branch(package, "main", "build-job")
        assert result is None

    def test_get_artifacts_by_mr(self):
        """Test getting artifacts through merge request"""
        # Mock setup
        package = Mock()

        # Mock merge request
        mock_mr = Mock()
        mock_mr.iid = 123

        # Test with existing merge request
        package.mergerequests.list.return_value = [mock_mr]
        package.artifacts.download.return_value = b"mock mr zip content"

        result = PkgGroupHandler.get_artifacts_by_mr(
            package, "feature-branch", "build-job"
        )
        assert result == b"mock mr zip content"
        package.artifacts.download.assert_called_once_with(
            job="build-job", ref_name="refs/merge-requests/123/head"
        )

        # Test with no merge requests
        package.artifacts.download.reset_mock()
        package.mergerequests.list.return_value = []

        result = PkgGroupHandler.get_artifacts_by_mr(
            package, "feature-branch", "build-job"
        )
        assert result is None
        package.artifacts.download.assert_not_called()

        # Test with exception
        package.mergerequests.list.side_effect = Exception("MR list failed")

        result = PkgGroupHandler.get_artifacts_by_mr(
            package, "feature-branch", "build-job"
        )
        assert result is None
