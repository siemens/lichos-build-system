import pytest
from unittest.mock import Mock, patch
from lichoscli.pkg import PkgGroupHandler
from tests import fixtures


class TestPkgGroupHandler:

    @pytest.fixture
    def pkg_handler(self):
        return fixtures.create_mock_pkg_handler()

    def test_init(self):
        mock_gitlab = fixtures.create_mock_gitlab()
        handler = PkgGroupHandler("test-group/pkg", mock_gitlab)
        assert handler.group_rpath == "test-group/pkg"
        assert handler.gitlab == mock_gitlab

    def test_get_all_packages(self, pkg_handler):
        packages = pkg_handler.get_all_packages()
        assert len(packages) == 4
        package_names = [pkg.name for pkg in packages]
        assert "package1" in package_names
        assert "package2" in package_names
        assert "package3" in package_names
        assert "package4" in package_names

    def test_get_package(self, pkg_handler):
        package = pkg_handler.get_package("package1")
        assert package.name == "package1"
        
        cached_package = pkg_handler.get_package("package1")
        assert cached_package == package

    def test_get_package_not_found(self, pkg_handler):
        package = pkg_handler.get_package("non-existent")
        assert package is None

    def test_update_package(self, pkg_handler):
        updated_pkg = pkg_handler.update_package(
            "package1", ci_config_path="new-ci.yml", branch="develop"
        )
        assert updated_pkg.ci_config_path == "new-ci.yml"
        assert updated_pkg.default_branch == "develop"

    def test_add_package(self, pkg_handler):
        with patch("lichoscli.utils.CIConfigUtils.get_ci_path", return_value=".gitlab-ci.yml"):
            new_pkg = pkg_handler.add_package(
                "new-package", branch="main", package_type="standard", subgroup=None
            )
            assert new_pkg.name == "new-package"

    def test_get_latest_pipeline(self, pkg_handler):
        mock_pipeline = fixtures.create_mock_pipeline()
        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = [mock_pipeline]

        pipeline = pkg_handler.get_latest_pipeline(pkg)
        assert pipeline.id == mock_pipeline.id

    def test_get_latest_pipeline_none(self, pkg_handler):
        pkg = pkg_handler.get_package("package1")
        pkg.pipelines.list.return_value = []

        pipeline = pkg_handler.get_latest_pipeline(pkg)
        assert pipeline is None

    def test_trigger_package_build(self, pkg_handler):
        package = Mock()
        package.name = "test-package"
        package.default_branch = "main"

        result = pkg_handler.trigger_package_build(package)
        assert result == 0
        package.pipelines.create.assert_called_once_with({'ref': 'main'})


    def test_get_artifacts_by_mr(self):
        package = Mock()
        mock_mr = Mock()
        mock_mr.iid = 123
        package.mergerequests.list.return_value = [mock_mr]
        package.artifacts.download.return_value = b"mock mr content"

        result = PkgGroupHandler.get_artifacts_by_mr(package, "feature-branch", "build-job")
        assert result == b"mock mr content"
