# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Tests for configuration and container factory."""

import pytest
from unittest.mock import Mock, patch
from argparse import Namespace

from lichoscli.core.config import ConfigBuilder, LichosConfig, ProviderType
from lichoscli.core.container_factory import DIContainerFactory
from lichoscli.providers.gitlab.container import GitLabServiceContainer
from lichoscli.ui import OutputBackend, PromptBackend, UserInterface


class TestConfigBuilder:
    """Test ConfigBuilder functionality."""
    
    def test_build_with_all_args(self):
        """Test building config when all arguments are provided."""
        args = Namespace(
            host="gitlab.example.com",
            pkg_group="platform/packages",
            branch="main",
            dry=False,
            debug=True,
            verbose=False,
            dump=False,
            output_backend="terminal",
            prompt_backend="terminal",
        )
        
        builder = ConfigBuilder(args)
        config = builder.build()
        
        assert config.host == "gitlab.example.com"
        assert config.pkg_group == "platform/packages"
        assert config.branch == "main"
        assert config.provider == ProviderType.GITLAB
        assert config.debug is True
        assert config.dry_run is False
        assert config.output_backend == OutputBackend.TERMINAL
        assert config.prompt_backend == PromptBackend.TERMINAL
    
    @patch('lichoscli.core.config.GitRepo')
    def test_build_with_git_auto_detect(self, mock_git_repo):
        """Test that host/pkg_group come from CI root and branch from current repo."""
        # CI root (00ci) provides host and pkg_group
        mock_ci_repo = Mock()
        mock_ci_repo.path = "/some/path/00ci"
        mock_ci_repo.remote_info = (
            "gitlab.example.com", "platform/packages", "00ci", "main"
        )
        mock_git_repo.auto_detect.return_value = mock_ci_repo

        # Current repo provides active branch but no remote info
        mock_current_repo = Mock()
        mock_current_repo.is_valid = True
        mock_current_repo.remote_info = None
        mock_current_repo.active_branch = "feat/my-feature"
        mock_git_repo.return_value = mock_current_repo

        args = Namespace(
            host=None, pkg_group=None, branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        config = ConfigBuilder(args).build()

        assert config.host == "gitlab.example.com"
        assert config.pkg_group == "platform/packages"
        assert config.branch == "feat/my-feature"  # from current repo, NOT CI root
        assert config.branch_explicitly_provided is False

    @patch('lichoscli.core.config.GitRepo')
    def test_build_local_repo_adopts_ci_root_group(self, mock_git_repo):
        """Test that local repo adopts CI root's host & group when both exist.

        Even though the local repo has its own remote info, the CI root
        provides the authoritative workspace-level group.  The local
        repo's ``_local_repo_info`` should cross-reference with the CI
        root so that both resolution paths yield the correct group.
        """
        # CI root (00ci) provides host and pkg_group
        mock_ci_repo = Mock()
        mock_ci_repo.path = "/some/path/00ci"
        mock_ci_repo.remote_info = (
            "gitlab.ci.com", "platform/ci", "00ci", "main"
        )
        mock_git_repo.auto_detect.return_value = mock_ci_repo

        # Current repo provides remote info and active branch
        mock_current_repo = Mock()
        mock_current_repo.is_valid = True
        mock_current_repo.remote_info = (
            "gitlab.local.com", "platform/local", "my-pkg", "feat/my-feature"
        )
        mock_current_repo.active_branch = "feat/my-feature"
        mock_git_repo.return_value = mock_current_repo

        args = Namespace(
            host=None, pkg_group=None, branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        config = ConfigBuilder(args).build()

        # Both CI root and local repo now resolve to the CI root's
        # host + group, so the result is the same regardless of order.
        assert config.host == "gitlab.ci.com"
        assert config.pkg_group == "platform/ci"
        # Branch still comes from the local repo
        assert config.branch == "feat/my-feature"
        assert config.branch_explicitly_provided is False

    @patch('lichoscli.core.config.GitRepo')
    def test_build_subgroup_uses_ci_root_group(self, mock_git_repo):
        """Test that subgroup packages resolve pkg_group from CI root, not local.

        When CWD is inside a subgroup package (e.g. apps/my-pkg), the local
        repo's URL yields a subgroup path as pkg_group.  The CI root (00ci)
        should win and provide the workspace-level group so that all packages
        are visible.
        """
        # CI root at workspace level
        mock_ci_repo = Mock()
        mock_ci_repo.path = "/workspace/pkg/00ci"
        mock_ci_repo.remote_info = (
            "gitlab.example.com", "your-group/platform-os/pkg", "00ci", "main"
        )
        mock_git_repo.auto_detect.return_value = mock_ci_repo

        # Local repo is in a subgroup (apps/)
        mock_current_repo = Mock()
        mock_current_repo.is_valid = True
        mock_current_repo.remote_info = (
            "gitlab.example.com", "your-group/platform-os/pkg/apps",
            "lichos-dummy-business-logic", "feat/my-feature",
        )
        mock_current_repo.active_branch = "feat/my-feature"
        mock_git_repo.return_value = mock_current_repo

        args = Namespace(
            host=None, pkg_group=None, branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        config = ConfigBuilder(args).build()

        # Must use the workspace-level group, NOT the subgroup
        assert config.pkg_group == "your-group/platform-os/pkg"
        assert config.host == "gitlab.example.com"
        assert config.branch == "feat/my-feature"

    @patch('lichoscli.core.config.GitRepo')
    def test_build_no_ci_root_falls_back_to_local(self, mock_git_repo):
        """Test that local repo is used when no CI root (00ci) exists."""
        mock_git_repo.auto_detect.return_value = None

        mock_current_repo = Mock()
        mock_current_repo.is_valid = True
        mock_current_repo.remote_info = (
            "gitlab.example.com", "my-org/my-group", "my-pkg", "main"
        )
        mock_current_repo.active_branch = "main"
        mock_git_repo.return_value = mock_current_repo

        args = Namespace(
            host=None, pkg_group=None, branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        config = ConfigBuilder(args).build()

        assert config.host == "gitlab.example.com"
        assert config.pkg_group == "my-org/my-group"
        assert config.branch == "main"
    
    @patch('lichoscli.core.config.GitRepo')
    def test_build_missing_required_fields(self, mock_git_repo):
        """Test that config is built with None values when fields are missing."""
        # Mock GitRepo.auto_detect() to return None (no git repo found)
        mock_git_repo.auto_detect.return_value = None
        mock_git_repo.return_value.is_valid = False
        mock_git_repo.return_value.active_branch = "main"
        
        args = Namespace(
            host=None,
            pkg_group=None,
            branch=None,
            dry=False,
            debug=False,
            verbose=False,
            dump=False,
            output_backend=None,
            prompt_backend=None,
        )
        
        builder = ConfigBuilder(args)
        config = builder.build()
        
        # Config should be built even with None values
        # Validation happens later when creating containers/clients
        assert config.host is None
        assert config.pkg_group is None
        assert config.branch is not None  # Should get from GitRepo.active_branch
    
    @patch('lichoscli.core.config.GitRepo')
    def test_branch_precedence_cli_wins(self, mock_git_repo):
        """CLI --branch beats env var and git active branch."""
        mock_git_repo.auto_detect.return_value = None
        mock_git_repo.return_value.active_branch = "from-git"

        args = Namespace(
            host="h", pkg_group="g", branch="from-cli",
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        with patch.dict("os.environ", {"LICHOS_BRANCH": "from-env"}):
            config = ConfigBuilder(args).build()

        assert config.branch == "from-cli"
        assert config.branch_explicitly_provided is True

    @patch('lichoscli.core.config.GitRepo')
    def test_branch_precedence_env_wins(self, mock_git_repo):
        """LICHOS_BRANCH env var beats git when CLI branch is None."""
        mock_git_repo.auto_detect.return_value = None
        mock_git_repo.return_value.active_branch = "from-git"

        args = Namespace(
            host="h", pkg_group="g", branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        with patch.dict("os.environ", {"LICHOS_BRANCH": "from-env"}):
            config = ConfigBuilder(args).build()

        assert config.branch == "from-env"
        assert config.branch_explicitly_provided is False

    @patch('lichoscli.core.config.GitRepo')
    def test_branch_precedence_git_fallback(self, mock_git_repo):
        """Git active branch is used when CLI and env var are both absent."""
        mock_git_repo.auto_detect.return_value = None
        mock_git_repo.return_value.active_branch = "from-git"

        args = Namespace(
            host="h", pkg_group="g", branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("LICHOS_BRANCH", None)
            config = ConfigBuilder(args).build()

        assert config.branch == "from-git"

    @patch('lichoscli.core.config.GitRepo')
    def test_backend_precedence_env_wins(self, mock_git_repo):
        """UI backend selection can be controlled via environment when CLI is unset."""
        mock_git_repo.auto_detect.return_value = None
        mock_git_repo.return_value.active_branch = "from-git"

        args = Namespace(
            host="h", pkg_group="g", branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        with patch.dict(
            "os.environ",
            {
                "LICHOS_OUTPUT_BACKEND": "terminal",
                "LICHOS_PROMPT_BACKEND": "terminal",
            },
        ):
            config = ConfigBuilder(args).build()

        assert config.output_backend == OutputBackend.TERMINAL
        assert config.prompt_backend == PromptBackend.TERMINAL
    
    def test_detect_provider_gitlab(self):
        """Test provider detection for GitLab."""
        provider = LichosConfig.detect_provider("gitlab.example.com")
        assert provider == ProviderType.GITLAB
    
    def test_detect_provider_github(self):
        """Test provider detection for GitHub."""
        provider = LichosConfig.detect_provider("github.com")
        assert provider == ProviderType.GITHUB


class TestDIContainerFactory:
    """Test DIContainerFactory functionality."""
    
    @patch('lichoscli.core.container_factory.GitLabClientFactory')
    def test_create_gitlab_container(self, mock_client_factory):
        """Test creating GitLab container."""
        config = LichosConfig(
            host="gitlab.example.com",
            pkg_group="platform/packages",
            branch="main",
            provider=ProviderType.GITLAB,
        )
        
        container = DIContainerFactory.create(config)
        
        assert isinstance(container, GitLabServiceContainer)
        assert container.group_rpath == "platform/packages"
        assert isinstance(container.obtain_ref(UserInterface), UserInterface)
    
    def test_create_github_container_not_implemented(self):
        """Test that GitHub container raises NotImplementedError."""
        config = LichosConfig(
            host="github.com",
            pkg_group="myorg/myrepo",
            branch="main",
            provider=ProviderType.GITHUB,
        )
        
        with pytest.raises(NotImplementedError) as exc_info:
            DIContainerFactory.create(config)
        
        assert "GitHub provider is not yet implemented" in str(exc_info.value)
    
    def test_create_unsupported_provider(self):
        """Test handling of unsupported provider type."""
        config = LichosConfig(
            host="bitbucket.org",
            pkg_group="myteam/myrepo",
            branch="main",
            provider="bitbucket",  # Not a valid ProviderType, but will test the else branch
        )
        
        # Need to manually set an invalid provider to test this branch
        # In real usage, this shouldn't happen due to type checking
        try:
            DIContainerFactory.create(config)
            assert False, "Should have raised ValueError"
        except (ValueError, AttributeError):
            # Either ValueError from our code or AttributeError from invalid provider
            pass
