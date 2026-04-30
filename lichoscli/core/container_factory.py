# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Factory for creating provider-specific DI containers."""

import logging
from typing import Any

from lichoscli.core.config import LichosConfig, ProviderType
from lichoscli.core.di import DIContainer
from lichoscli.providers.gitlab import GitLabClientFactory
from lichoscli.providers.gitlab.container import GitLabServiceContainer
from lichoscli.ui import UserInterface, UserInterfaceFactory

logger = logging.getLogger(__name__)


class DIContainerFactory:
    """Factory to create the appropriate DI container based on provider type."""
    
    @staticmethod
    def create(config: LichosConfig) -> DIContainer:
        """
        Create and return the appropriate DI container based on the provider.
        
        Args:
            config: LichosConfig object containing provider and connection information
            
        Returns:
            DIContainer: Provider-specific DI container instance
            
        Raises:
            ValueError: If the provider type is not supported
        """
        if config.provider == ProviderType.GITLAB:
            container = DIContainerFactory._create_gitlab_container(config)
        elif config.provider == ProviderType.GITHUB:
            container = DIContainerFactory._create_github_container(config)
        else:
            raise ValueError(f"Unsupported provider type: {config.provider}")

        container.register_reference(
            UserInterface,
            UserInterfaceFactory.create(
                output_backend=config.output_backend,
                prompt_backend=config.prompt_backend,
            ),
        )
        return container
    
    @staticmethod
    def _create_gitlab_container(config: LichosConfig) -> GitLabServiceContainer:
        """Create GitLab-specific DI container."""
        def client_factory() -> Any:
            return GitLabClientFactory(config.host).create()
        
        logger.debug("Creating GitLab DI container for host: %s", config.host)
        return GitLabServiceContainer(config.pkg_group, client_factory)
    
    @staticmethod
    def _create_github_container(config: LichosConfig) -> DIContainer:
        """Create GitHub-specific DI container."""
        # TODO: Implement GitHub container when GitHub provider is added
        raise NotImplementedError("GitHub provider is not yet implemented")
