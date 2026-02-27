# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import unittest
from unittest.mock import MagicMock, patch

import git
import pytest
from git.exc import InvalidGitRepositoryError

from lichoscli.utils import BuildUtils, CIConfigUtils
from lichoscli.core.models.git import GitRepo, GitUrl


class TestGitRepo:
    """Tests for GitRepo class (migrated from GitUtils)"""

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_active_branch_success(self, mock_repo_cls):
        """Test successful branch retrieval"""
        mock_repo = MagicMock()
        mock_repo.active_branch.name = "feature/test-branch"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.active_branch == "feature/test-branch"

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_group_success_ssh(self, mock_repo_cls):
        """Test successful group extraction from SSH URL"""
        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "git@gitlab.com:your-group/platform-os/mypackage.git"
        # active_branch is needed for remote_info
        mock_repo.active_branch.name = "main"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.group == "your-group/platform-os"

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_group_success_no_git_extension(self, mock_repo_cls):
        """Test successful group extraction from URL without .git"""
        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "git@gitlab.com:your-group/platform-os/mypackage"
        mock_repo.active_branch.name = "main"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.group == "your-group/platform-os"

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_group_invalid_url(self, mock_repo_cls):
        """Test group extraction with invalid URL format"""
        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "https://invalid-url-format"
        mock_repo.active_branch.name = "main"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.group == ""

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_package_name_success(self, mock_repo_cls):
        """Test successful package name extraction"""
        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "git@gitlab.com:your-group/platform-os/mypackage.git"
        mock_repo.active_branch.name = "main"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.package_name == "mypackage"

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_package_name_no_git_extension(self, mock_repo_cls):
        """Test package name extraction without .git extension"""
        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "git@gitlab.com:your-group/platform-os/mypackage"
        mock_repo.active_branch.name = "main"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.package_name == "mypackage"

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_package_name_invalid_url(self, mock_repo_cls):
        """Test package name extraction with invalid URL"""
        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "https://invalid-url"
        mock_repo.active_branch.name = "main"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.package_name == ""

    def test_sanitize_branch_name_ending_with_main(self):
        """Test branch name ending with /main"""
        result = GitUrl.sanitize_branch_name("feature/branch/main")
        assert result == "feature/branch/*"

    def test_sanitize_branch_name_not_ending_with_main(self):
        """Test branch name not ending with /main"""
        result = GitUrl.sanitize_branch_name("feature/branch")
        assert result == "feature/branch"

    def test_sanitize_branch_name_main_in_middle(self):
        """Test branch name with 'main' in the middle"""
        result = GitUrl.sanitize_branch_name("feature/main/branch")
        assert result == "feature/main/branch"

    def test_sanitize_branch_name_exactly_main(self):
        """Test branch name that is exactly 'main'"""
        result = GitUrl.sanitize_branch_name("main")
        assert result == "main"

    def test_sanitize_branch_name_empty(self):
        """Test empty branch name"""
        result = GitUrl.sanitize_branch_name("")
        assert result == ""

    def test_slugify_ref_normal(self):
        """Test normal branch name conversion"""
        result = GitUrl.slugify_ref("feature/my-branch")
        assert result == "feature-my-branch"

    def test_slugify_ref_special_chars(self):
        """Test branch name with special characters"""
        result = GitUrl.slugify_ref("feature/my_branch@2023!")
        assert result == "feature-my-branch-2023"

    def test_slugify_ref_uppercase(self):
        """Test uppercase branch name"""
        result = GitUrl.slugify_ref("FEATURE/MY-BRANCH")
        assert result == "feature-my-branch"

    def test_slugify_ref_long_truncation(self):
        """Test that long branch names are truncated to 63 characters"""
        long_name = "a" * 100
        result = GitUrl.slugify_ref(long_name)
        assert len(result) == 63
        assert result == "a" * 63

    def test_slugify_ref_leading_trailing_dashes(self):
        """Test branch name that would result in leading/trailing dashes"""
        result = GitUrl.slugify_ref("_feature/branch_")
        assert result == "feature-branch"

    def test_slugify_ref_empty(self):
        """Test empty branch name"""
        result = GitUrl.slugify_ref("")
        assert result == ""


class TestGitUrlParsing:
    """Tests for GitUrl parsing (including web URLs and branch extraction)"""

    def test_parse_gitlab_web_url_basic(self):
        """Test parsing basic GitLab web URL"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch is None

    def test_parse_gitlab_web_url_with_subgroups(self):
        """Test parsing GitLab web URL with multiple subgroups"""
        result = GitUrl.parse("https://gitlab.example.com/group/subgroup1/subgroup2/test-package")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group/subgroup1/subgroup2"
        assert result.package == "test-package"
        assert result.branch is None

    def test_parse_gitlab_web_url_with_branch(self):
        """Test parsing GitLab web URL with branch"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package/-/tree/feature-branch")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch == "feature-branch"

    def test_parse_gitlab_web_url_with_branch_and_slashes(self):
        """Test parsing GitLab web URL with branch containing slashes"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package/-/tree/feature/my-branch")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch == "feature/my-branch"

    def test_parse_gitlab_web_url_with_git_extension(self):
        """Test parsing GitLab web URL with .git extension"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package.git")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch is None

    def test_parse_gitlab_web_url_with_trailing_slash(self):
        """Test parsing GitLab web URL with trailing slash"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package/")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch is None

    def test_parse_gitlab_web_url_with_query_params(self):
        """Test parsing GitLab web URL with query parameters"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package?tab=activity")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch is None

    def test_parse_gitlab_web_url_http(self):
        """Test parsing GitLab web URL with http protocol"""
        result = GitUrl.parse("http://gitlab.example.com/group/test-package")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch is None

    def test_parse_gitlab_web_url_invalid_too_short(self):
        """Test parsing invalid GitLab web URL (too short)"""
        result = GitUrl.parse("https://gitlab.example.com/test-package")
        assert result is None

    def test_parse_gitlab_web_url_invalid_not_url(self):
        """Test parsing invalid input (not a URL)"""
        result = GitUrl.parse("test-package")
        assert result is None

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.example.com/group/test-package",
            "https://gitlab.example.com/group/subgroup1/subgroup2/test-package",
            "https://gitlab.example.com/group/test-package/-/tree/feature-branch",
            "https://gitlab.example.com/group/test-package/-/tree/feature/my-branch",
            "https://gitlab.example.com/group/test-package.git",
            "https://gitlab.example.com/group/test-package/",
            "https://gitlab.example.com/group/test-package?tab=activity",
            "http://gitlab.example.com/group/test-package",
            "ssh://git@gitlab.example.com/group/test-package.git",
            "git@gitlab.example.com:group/test-package.git",
        ],
    )
    def test_parse_gitlab_url_variants_parsable(self, url):
        """Test parsing supported GitLab URL variants"""
        result = GitUrl.parse(url)
        assert result is not None

    def test_parse_gitlab_web_url_ssh_url(self):
        """Test parsing SSH URL with scp-style syntax"""
        result = GitUrl.parse("git@gitlab.example.com:group/test-package.git")
        assert result is not None
        assert result.host == "gitlab.example.com"
        assert result.group == "group"
        assert result.package == "test-package"
        assert result.branch is None

    def test_clone_url_from_web_url(self):
        """Test clone_url property converts web URL to SSH clone URL"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package")
        assert result is not None
        assert result.clone_url == "git@gitlab.example.com:group/test-package.git"

    def test_clone_url_from_web_url_with_branch(self):
        """Test clone_url property strips branch from URL"""
        result = GitUrl.parse("https://gitlab.example.com/group/test-package/-/tree/feature-branch")
        assert result is not None
        assert result.clone_url == "git@gitlab.example.com:group/test-package.git"

    def test_clone_url_from_ssh_url(self):
        """Test clone_url property normalizes SSH URL format"""
        result = GitUrl.parse("git@gitlab.example.com:group/test-package.git")
        assert result is not None
        assert result.clone_url == "git@gitlab.example.com:group/test-package.git"

    def test_clone_url_with_subgroups(self):
        """Test clone_url property with multi-level groups"""
        result = GitUrl.parse("https://gitlab.example.com/group/subgroup1/subgroup2/test-package")
        assert result is not None
        assert result.clone_url == "git@gitlab.example.com:group/subgroup1/subgroup2/test-package.git"

    def test_clone_url_from_ssh_protocol_url(self):
        """Test clone_url property converts ssh:// protocol URL to SCP-style"""
        result = GitUrl.parse("ssh://git@gitlab.example.com/group/test-package.git")
        assert result is not None
        assert result.clone_url == "git@gitlab.example.com:group/test-package.git"


    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_has_submodules_true(self, mock_repo_cls):
        """Test has_submodules returns True when git output confirms it"""
        mock_repo = MagicMock()
        mock_repo.git.ls_tree.return_value = "160000 commit 1234567890abcdef\tpath/to/submodule"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.has_submodules is True

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_has_submodules_false(self, mock_repo_cls):
        """Test has_submodules returns False when no submodules"""
        mock_repo = MagicMock()
        mock_repo.git.ls_tree.return_value = "100644 blob ... file.txt"
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        assert repo.has_submodules is False

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_update_submodules_success(self, mock_repo_cls):
        """Test successful submodule initialization"""
        mock_repo = MagicMock()
        mock_repo.git.ls_tree.return_value = "160000 commit ..." # ensure has_submodules is True
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        result = repo.update_submodules()
        assert result is True
        mock_repo.git.submodule.assert_called_with("update", "--init", "--recursive")

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_update_submodules_no_submodules(self, mock_repo_cls):
        """Test update_submodules when no submodules exist"""
        mock_repo = MagicMock()
        mock_repo.git.ls_tree.return_value = ""
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        result = repo.update_submodules()
        assert result is True
        mock_repo.git.submodule.assert_not_called()

    @patch("lichoscli.core.models.git.git_repo.Repo")
    def test_update_submodules_git_error(self, mock_repo_cls):
        """Test update_submodules when git command fails"""
        mock_repo = MagicMock()
        mock_repo.git.ls_tree.return_value = "160000 commit ..."
        mock_repo.git.submodule.side_effect = git.exc.GitCommandError("submodule", 1)
        mock_repo_cls.return_value = mock_repo

        repo = GitRepo(".")
        result = repo.update_submodules()
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
        result = CIConfigUtils.get_ci_path("your-group/platform-os", branch="feature-branch")
        expected = "gbp.yml@your-group/platform-os/00ci:feature-branch"
        assert result == expected

    def test_get_ci_path_custom_type_with_branch(self):
        """Test CI path generation with custom type and branch"""
        result = CIConfigUtils.get_ci_path("your-group/platform-os", ci_typ="image", branch="develop")
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
