# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Tests for configuration and container factory."""

import pytest
from unittest.mock import Mock, patch
from argparse import Namespace

from lichoscli.core.config import ConfigBuilder, LichosConfig, ContainerRuntime, ProviderType
from lichoscli.core.container_factory import DIContainerFactory
from lichoscli.providers.gitlab.container import GitLabServiceContainer
from lichoscli.providers.docker import DockerContainerService
from lichoscli.providers.podman import PodmanContainerService
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
    
    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_build_anchor_provides_host_and_group(self, mock_git_repo, mock_anchor_cls):
        """Test that .lichos anchor provides host/pkg_group, branch from local repo."""
        mock_anchor_cls.return_value.read.return_value = {
            "host": "gitlab.example.com",
            "pkg_group": "platform/packages",
        }

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
        assert config.branch == "feat/my-feature"
        assert config.branch_explicitly_provided is False

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_build_anchor_wins_over_local_repo(self, mock_git_repo, mock_anchor_cls):
        """Test that .lichos anchor takes precedence over local git repo.

        Even though the local repo has its own remote info, the anchor
        provides the authoritative workspace-level group.
        """
        mock_anchor_cls.return_value.read.return_value = {
            "host": "anchor-host.example.com",
            "pkg_group": "platform/root",
        }

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

        assert config.host == "anchor-host.example.com"
        assert config.pkg_group == "platform/root"
        assert config.branch == "feat/my-feature"
        assert config.branch_explicitly_provided is False

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_build_anchor_resolves_subgroup(self, mock_git_repo, mock_anchor_cls):
        """Test that .lichos anchor resolves correct group for subgroup packages.

        When CWD is inside a subgroup package (e.g. apps/my-pkg), the local
        repo's URL yields a subgroup path as pkg_group.  The .lichos anchor
        provides the workspace-level group so that all packages are visible.
        """
        mock_anchor_cls.return_value.read.return_value = {
            "host": "gitlab.example.com",
            "pkg_group": "your-group/platform-os/pkg",
        }

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

        assert config.pkg_group == "your-group/platform-os/pkg"
        assert config.host == "gitlab.example.com"
        assert config.branch == "feat/my-feature"

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_build_no_anchor_falls_back_to_local(self, mock_git_repo, mock_anchor_cls):
        """Test that local repo is used when no .lichos anchor exists."""
        mock_anchor_cls.return_value.read.return_value = None

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

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_build_anchor_wins_over_xdg(self, mock_git_repo, mock_anchor_cls):
        """Test that .lichos anchor takes precedence over XDG config."""
        mock_anchor_cls.return_value.read.return_value = {
            "host": "lichos-host.example.com",
            "pkg_group": "lichos/group",
        }

        mock_current_repo = Mock()
        mock_current_repo.is_valid = False
        mock_current_repo.active_branch = "main"
        mock_git_repo.return_value = mock_current_repo

        args = Namespace(
            host=None, pkg_group=None, branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )

        config = ConfigBuilder(args).build()

        assert config.host == "lichos-host.example.com"
        assert config.pkg_group == "lichos/group"

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.UserConfigStore')
    @patch('lichoscli.core.config.GitRepo')
    def test_build_missing_required_fields(self, mock_git_repo, mock_config_store, mock_anchor_cls):
        """Test that config is built with None values when fields are missing."""
        mock_anchor_cls.return_value.read.return_value = None
        mock_git_repo.return_value.is_valid = False
        mock_git_repo.return_value.active_branch = "main"
        mock_config_store.read.return_value = {}
        
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
    
    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_branch_precedence_cli_wins(self, mock_git_repo, mock_anchor_cls):
        """CLI --branch beats env var and git active branch."""
        mock_anchor_cls.return_value.read.return_value = None
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

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_branch_precedence_env_wins(self, mock_git_repo, mock_anchor_cls):
        """LICHOS_BRANCH env var beats git when CLI branch is None."""
        mock_anchor_cls.return_value.read.return_value = None
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

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_branch_precedence_git_fallback(self, mock_git_repo, mock_anchor_cls):
        """Git active branch is used when CLI and env var are both absent."""
        mock_anchor_cls.return_value.read.return_value = None
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

    @patch('lichoscli.core.config.LichosAnchorHandler')
    @patch('lichoscli.core.config.GitRepo')
    def test_backend_precedence_env_wins(self, mock_git_repo, mock_anchor_cls):
        """UI backend selection can be controlled via environment when CLI is unset."""
        mock_anchor_cls.return_value.read.return_value = None
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

    @patch("lichoscli.core.config.LichosAnchorHandler")
    @patch("lichoscli.core.config.GitRepo")
    def test_container_runtime_defaults_to_docker(self, mock_git_repo, mock_anchor_cls):
        """No stored runtime -> default docker."""
        mock_anchor_cls.return_value.read.return_value = None
        mock_git_repo.return_value.active_branch = "main"
        args = Namespace(
            host="h", pkg_group="g", branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )
        with patch("lichoscli.core.config.UserConfigStore.read", return_value={}):
            cfg = ConfigBuilder(args).build()
        assert cfg.container_runtime == ContainerRuntime.DOCKER

    @patch("lichoscli.core.config.LichosAnchorHandler")
    @patch("lichoscli.core.config.GitRepo")
    def test_container_runtime_resolves_podman_from_user_config(self, mock_git_repo, mock_anchor_cls):
        """Stored runtime 'podman' -> ContainerRuntime.PODMAN."""
        mock_anchor_cls.return_value.read.return_value = None
        mock_git_repo.return_value.active_branch = "main"
        args = Namespace(
            host="h", pkg_group="g", branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )
        with patch("lichoscli.core.config.UserConfigStore.read", return_value={"container_runtime": "podman"}):
            cfg = ConfigBuilder(args).build()
        assert cfg.container_runtime == ContainerRuntime.PODMAN

    @patch("lichoscli.core.config.LichosAnchorHandler")
    @patch("lichoscli.core.config.GitRepo")
    def test_container_runtime_invalid_value_falls_back_to_docker(self, mock_git_repo, mock_anchor_cls):
        """Garbage value in user config should fall back to docker, not crash."""
        mock_anchor_cls.return_value.read.return_value = None
        mock_git_repo.return_value.active_branch = "main"
        args = Namespace(
            host="h", pkg_group="g", branch=None,
            dry=False, debug=False, verbose=False, dump=False,
            output_backend=None, prompt_backend=None,
        )
        with patch("lichoscli.core.config.UserConfigStore.read", return_value={"container_runtime": "rkt"}):
            cfg = ConfigBuilder(args).build()
        assert cfg.container_runtime == ContainerRuntime.DOCKER


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

    @patch('lichoscli.core.container_factory.GitLabClientFactory')
    def test_create_gitlab_container_default_runtime_is_docker(self, mock_client_factory):
        """By default the factory wires DockerContainerService."""
        from lichoscli.core.services import ContainerService
        config = LichosConfig(
            host="gitlab.example.com",
            pkg_group="platform/packages",
            branch="main",
            provider=ProviderType.GITLAB,
        )
        container = DIContainerFactory.create(config)
        svc = container.obtain_ref(ContainerService)
        assert isinstance(svc, DockerContainerService)
        assert not isinstance(svc, PodmanContainerService)

    @patch('lichoscli.core.container_factory.GitLabClientFactory')
    def test_create_gitlab_container_podman_runtime(self, mock_client_factory):
        """container_runtime=podman -> PodmanContainerService."""
        from lichoscli.core.services import ContainerService
        config = LichosConfig(
            host="gitlab.example.com",
            pkg_group="platform/packages",
            branch="main",
            provider=ProviderType.GITLAB,
            container_runtime=ContainerRuntime.PODMAN,
        )
        container = DIContainerFactory.create(config)
        assert container.container_runtime == ContainerRuntime.PODMAN
        svc = container.obtain_ref(ContainerService)
        assert isinstance(svc, PodmanContainerService)
    
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
