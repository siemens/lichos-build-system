import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import pytest
import git
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from lichoscli.utils import BuildUtils, CIConfigUtils, GitUtils


class TestGitUtils:
    """Complete tests for GitUtils class"""

    @patch("git.Repo")
    def test_get_branch_success(self, mock_repo):
        """Test successful branch retrieval"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.active_branch.name = "feature/test-branch"

        result = GitUtils.get_branch(mock_repo_instance)
        assert result == "feature/test-branch"

    @patch("git.Repo")
    def test_get_group_success_ssh(self, mock_repo):
        """Test successful group extraction from SSH URL"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = (
            "git@gitlab.com:your-group/platform-os/mypackage.git"
        )

        result = GitUtils.get_group(mock_repo_instance)
        assert result == "your-group/platform-os"

    @patch("git.Repo")
    def test_get_group_success_no_git_extension(self, mock_repo):
        """Test successful group extraction from URL without .git"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = (
            "git@gitlab.com:your-group/platform-os/mypackage"
        )

        result = GitUtils.get_group(mock_repo_instance)
        assert result == "your-group/platform-os"

    @patch("git.Repo")
    def test_get_group_invalid_url(self, mock_repo):
        """Test group extraction with invalid URL format"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = "https://invalid-url-format"

        result = GitUtils.get_group(mock_repo_instance)
        assert result == ""

    @patch("git.Repo")
    def test_get_package_name_success(self, mock_repo):
        """Test successful package name extraction"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = (
            "git@gitlab.com:your-group/platform-os/mypackage.git"
        )

        result = GitUtils.get_package_name_from_git_repo(mock_repo_instance)
        assert result == "mypackage"

    @patch("git.Repo")
    def test_get_package_name_no_git_extension(self, mock_repo):
        """Test package name extraction without .git extension"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = (
            "git@gitlab.com:your-group/platform-os/mypackage"
        )

        result = GitUtils.get_package_name_from_git_repo(mock_repo_instance)
        assert result == "mypackage"

    @patch("git.Repo")
    def test_get_package_name_invalid_url(self, mock_repo):
        """Test package name extraction with invalid URL"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = "https://invalid-url"

        result = GitUtils.get_package_name_from_git_repo(mock_repo_instance)
        assert result == ""

    @patch("git.Repo")
    def test_get_package_name_exception(self, mock_repo):
        """Test package name extraction with exception"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.side_effect = Exception("Remote error")

        result = GitUtils.get_package_name_from_git_repo(mock_repo_instance)
        assert result == ""

    @patch("lichoscli.utils.Repo")
    def test_get_git_repo_success(self, mock_repo):
        """Test successful git repo retrieval"""
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        result = GitUtils.get_git_repo("/path/to/repo")
        assert result == mock_repo_instance
        mock_repo.assert_called_once_with("/path/to/repo")

    @patch("lichoscli.utils.Repo")
    def test_get_git_repo_invalid(self, mock_repo):
        """Test git repo retrieval with invalid repo"""
        mock_repo.side_effect = InvalidGitRepositoryError

        result = GitUtils.get_git_repo("/invalid/path")
        assert result is None

    def test_delete_main_from_branch_name_ending_with_main(self):
        """Test branch name ending with /main"""
        result = GitUtils.delete_main_from_branch_name("feature/branch/main")
        assert result == "feature/branch/*"

    def test_delete_main_from_branch_name_not_ending_with_main(self):
        """Test branch name not ending with /main"""
        result = GitUtils.delete_main_from_branch_name("feature/branch")
        assert result == "feature/branch"

    def test_delete_main_from_branch_name_main_in_middle(self):
        """Test branch name with 'main' in the middle"""
        result = GitUtils.delete_main_from_branch_name("feature/main/branch")
        assert result == "feature/main/branch"

    def test_delete_main_from_branch_name_exactly_main(self):
        """Test branch name that is exactly 'main'"""
        result = GitUtils.delete_main_from_branch_name("main")
        assert result == "main"

    def test_delete_main_from_branch_name_empty(self):
        """Test empty branch name"""
        result = GitUtils.delete_main_from_branch_name("")
        assert result == ""

    def test_get_ref_slug_normal(self):
        """Test normal branch name conversion"""
        result = GitUtils.get_ref_slug("feature/my-branch")
        assert result == "feature-my-branch"

    def test_get_ref_slug_special_chars(self):
        """Test branch name with special characters"""
        result = GitUtils.get_ref_slug("feature/my_branch@2023!")
        assert result == "feature-my-branch-2023"

    def test_get_ref_slug_uppercase(self):
        """Test uppercase branch name"""
        result = GitUtils.get_ref_slug("FEATURE/MY-BRANCH")
        assert result == "feature-my-branch"

    def test_get_ref_slug_long_truncation(self):
        """Test that long branch names are truncated to 63 characters"""
        long_name = "a" * 100
        result = GitUtils.get_ref_slug(long_name)
        assert len(result) == 63
        assert result == "a" * 63

    def test_get_ref_slug_leading_trailing_dashes(self):
        """Test branch name that would result in leading/trailing dashes"""
        result = GitUtils.get_ref_slug("_feature/branch_")
        assert result == "feature-branch"

    def test_get_ref_slug_empty(self):
        """Test empty branch name"""
        result = GitUtils.get_ref_slug("")
        assert result == ""

    @patch("git.Repo")
    def test_get_main_group_from_git_url(self, mock_repo):
        """Test main group extraction from Git URL"""
        mock_repo_instance = MagicMock()
        mock_repo_instance.remotes.origin.url = (
            "git@gitlab.com:your-group/platform-os/pkg/test"
        )
        data = GitUtils.parse_repo_data(mock_repo_instance)
        assert data is not None
        result = GitUtils.get_main_group(data[1])
        assert result == "your-group/platform-os/pkg"

    @patch("os.path.exists")
    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_has_submodules_with_gitmodules_file(self, mock_get_repo, mock_exists):
        """Test has_submodules returns True when .gitmodules exists"""
        mock_repo = MagicMock()
        mock_repo.working_dir = "/test/repo"
        mock_get_repo.return_value = mock_repo
        mock_exists.return_value = True

        result = GitUtils.has_submodules()
        assert result is True
        mock_exists.assert_called_once_with("/test/repo/.gitmodules")

    @patch("os.path.exists")
    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_has_submodules_without_gitmodules_file(self, mock_get_repo, mock_exists):
        """Test has_submodules returns False when .gitmodules doesn't exist"""
        mock_repo = MagicMock()
        mock_repo.working_dir = "/test/repo"
        mock_get_repo.return_value = mock_repo
        mock_exists.return_value = False

        result = GitUtils.has_submodules()
        assert result is False
        mock_exists.assert_called_once_with("/test/repo/.gitmodules")

    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_has_submodules_no_repo(self, mock_get_repo):
        """Test has_submodules returns False when no git repo is found"""
        mock_get_repo.return_value = None

        result = GitUtils.has_submodules()
        assert result is False

    @patch("lichoscli.utils.GitUtils.has_submodules")
    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_initialize_submodules_success(self, mock_get_repo, mock_has_submodules):
        """Test successful submodule initialization"""
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_has_submodules.return_value = True

        result = GitUtils.initialize_submodules()
        assert result is True
        mock_repo.git.submodule.assert_any_call('init')
        mock_repo.git.submodule.assert_any_call('update', '--recursive')

    @patch("lichoscli.utils.GitUtils.has_submodules")
    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_initialize_submodules_no_submodules(self, mock_get_repo, mock_has_submodules):
        """Test initialize_submodules when no submodules exist"""
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_has_submodules.return_value = False

        result = GitUtils.initialize_submodules()
        assert result is True
        mock_repo.git.submodule.assert_not_called()

    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_initialize_submodules_no_repo(self, mock_get_repo):
        """Test initialize_submodules when no git repo is found"""
        mock_get_repo.return_value = None

        result = GitUtils.initialize_submodules()
        assert result is False

    @patch("lichoscli.utils.GitUtils.has_submodules")
    @patch("lichoscli.utils.GitUtils.get_git_repo")
    def test_initialize_submodules_git_command_error(self, mock_get_repo, mock_has_submodules):
        """Test initialize_submodules when git command fails"""
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_has_submodules.return_value = True
        mock_repo.git.submodule.side_effect = git.exc.GitCommandError("submodule", 1)

        result = GitUtils.initialize_submodules()
        assert result is False


class TestCIConfigUtils:
    """Complete tests for CIConfigUtils class"""

    def test_get_ci_path_default(self):
        """Test CI path generation with default pipeline name"""
        result = CIConfigUtils.get_ci_path("your-group/platform-os")
        expected = "gbp.yml@your-group/platform-os/00ci"
        assert result == expected

    def test_get_ci_path_custom_type(self):
        """Test CI path generation with custom CI type"""
        result = CIConfigUtils.get_ci_path("your-group/platform-os", ci_typ="image")
        expected = "image.yml@your-group/platform-os/00ci"
        assert result == expected

    def test_get_ci_path_with_branch(self):
        """Test CI path generation with branch specified"""
        result = CIConfigUtils.get_ci_path(
            "your-group/platform-os", branch="feature-branch"
        )
        expected = "gbp.yml@your-group/platform-os/00ci:feature-branch"
        assert result == expected

    def test_get_ci_path_custom_type_with_branch(self):
        """Test CI path generation with custom type and branch"""
        result = CIConfigUtils.get_ci_path(
            "your-group/platform-os", ci_typ="image", branch="develop"
        )
        expected = "image.yml@your-group/platform-os/00ci:develop"
        assert result == expected

    @patch("subprocess.run")
    def test_pull_docker_image_success_unittest(self, mock_run):
        """Test successful Docker image pull"""
        mock_run.return_value.returncode = 0

        result = BuildUtils.pull_docker_image("debian:11")

        assert result == 0
        mock_run.assert_called_once_with(("docker", "pull", "debian:11"), check=False)

    @patch("subprocess.run")
    def test_pull_docker_image_failure_unittest(self, mock_run):
        """Test failed Docker image pull"""
        mock_run.return_value.returncode = 1

        result = BuildUtils.pull_docker_image("invalid:image")

        assert result == 1

    def test_build_script_command_unittest(self):
        """Test script command building"""
        result = BuildUtils.build_script_command("apt update", "make install")
        assert result == "apt update ; make install"


if __name__ == "__main__":
    # Run pytest for the pytest-style tests
    pytest.main([__file__, "-v"])

    # Run unittest for the unittest-style tests
    unittest.main(verbosity=2)
