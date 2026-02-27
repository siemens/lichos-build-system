# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab dependency injection container implementation."""

import logging
import os
from typing import Any, TypeVar, Callable, Optional

from lichoscli.core.di import DIContainer, ReferenceNotFoundError
from lichoscli.core.models.git.git_url import GitUrl
from lichoscli.core.services import (
    BuildInfoService,
    CacheService,
    ContainerService,
    DependencyService,
    EditorStrategy,
    EnvironmentService,
    NotifyService,
    PackageService,
    RepoParserService,
    SourceCollectionService,
    StorageService,
    WorkspaceService,
)
from lichoscli.providers.gitlab.factory import GitLabServiceFactory
from lichoscli.providers.vscode import VSCodeEditorStrategy

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GitLabServiceContainer(DIContainer):
    """GitLab-specific dependency injection container."""

    def __init__(self, group_rpath: Optional[str], gitlab_factory: Callable[[], Any]):
        """Initialize the GitLab service container."""
        self.group_rpath = group_rpath
        self._gitlab_factory = gitlab_factory
        self._gitlab_client = None
        self._group_id = None
        self.project_id = os.environ.get("CI_PROJECT_ID")

        self._services: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._editor_strategies: dict[str, Any] = {}
        self._initialize_services()

    @property
    def gitlab(self):
        if self._gitlab_client is None:
            self._gitlab_client = self._gitlab_factory()
        return self._gitlab_client

    def _initialize_services(self) -> None:
        """Initialize and register all GitLab services."""
        
        factory = GitLabServiceFactory(self)

        self._services[GitUrl] = GitUrl()
        self._factories[CacheService] = factory.create_cache_service
        self._factories[PackageService] = factory.create_package_service
        self._factories[BuildInfoService] = factory.create_buildinfo_service
        self._factories[DependencyService] = factory.create_dependency_service
        self._factories[WorkspaceService] = factory.create_workspace_service
        self._factories[ContainerService] = factory.create_container_service
        self._factories[EnvironmentService] = factory.create_environment_service
        self._factories[RepoParserService] = factory.create_repo_parser_service
        self._factories[SourceCollectionService] = factory.create_source_collection_service

        vscode_editor_strategy = VSCodeEditorStrategy()
        self._editor_strategies = {"code": vscode_editor_strategy}

        if self.project_id:
            self._factories[StorageService] = factory.create_gitlab_storage_service
            self._factories[NotifyService] = factory.create_gitlab_notify_service

            logger.debug(
                "Registered GitLab storage and notification services with shared issue writer for project %s",
                self.project_id,
            )
        else:
            self._factories[StorageService] = factory.create_fs_storage_service
            self._factories[NotifyService] = factory.create_fs_notify_service

            logger.debug("Registered filesystem storage and notification services for local execution")

    def obtain_ref(self, ref_type: type[T]) -> T:
        if ref_type in self._services:
            return self._services[ref_type]

        if ref_type in self._factories:
            instance = self._factories[ref_type]()
            self._services[ref_type] = instance
            return instance

        raise ReferenceNotFoundError(f"Service {ref_type.__name__} is not registered")

    def get_editor_strategy(self, editor_name: str) -> EditorStrategy:
        """Get an editor strategy by name."""
        if editor_name not in self._editor_strategies:
            raise ReferenceNotFoundError(f"Editor strategy '{editor_name}' is not registered")

        return self._editor_strategies[editor_name]

    def register_reference(self, reference_type: type[T], implementation: T) -> None:
        """Register a service implementation for a given type."""
        self._services[reference_type] = implementation
        logger.debug("Registered service %s", reference_type.__name__)
