"""GitLab dependency injection container implementation."""

import logging
import os
from typing import Any, Dict, Type, TypeVar

from lichoscli.core.di import DIContainer, ReferenceNotFoundError
from lichoscli.core.services import (
    BuildInfoService,
    CacheService,
    ContainerService,
    DependencyService,
    EditorStrategy,
    EnvironmentService,
    NotifyService,
    PackageService,
    StorageService,
    WorkspaceService,
)
from lichoscli.providers.docker import DockerContainerService
from lichoscli.providers.filesystem import (
    FilesystemNotifyService,
    FilesystemStorageService,
)
from lichoscli.providers.filesystem.cache_service import DiskCacheService
from lichoscli.providers.gitlab.services.buildinfo_service import GitLabBuildInfoService
from lichoscli.providers.gitlab.services.dependency_service import (
    GitLabDependencyService,
)
from lichoscli.providers.gitlab.services.environment_service import (
    GitLabEnvironmentService,
)
from lichoscli.providers.gitlab.services.gitlab_issue_writer import GitLabIssueWriter
from lichoscli.providers.gitlab.services.notify_service import GitLabNotifyService
from lichoscli.providers.gitlab.services.package_service import GitLabPackageService
from lichoscli.providers.gitlab.services.storage_service import GitLabStorageService
from lichoscli.providers.gitlab.services.workspace_service import GitLabWorkspaceService
from lichoscli.providers.vscode import VSCodeEditorStrategy

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GitLabServiceContainer(DIContainer):
    """GitLab-specific dependency injection container."""

    def __init__(self, group_rpath: str, gitlab):
        """
        Initialize the GitLab service container.

        Args:
            group_rpath: The GitLab group relative path
            gitlab: The GitLab client instance
        """
        self.group_rpath = group_rpath
        self.gitlab = gitlab
        self.group_id = gitlab.groups.get(group_rpath).id
        self.project_id = os.environ.get("CI_PROJECT_ID")

        self._services: Dict[Type, Any] = {}
        self._initialize_services()

    def _initialize_services(self) -> None:
        """Initialize and register all GitLab services."""

        cache_service = DiskCacheService(default_ttl=60 * 60 * 24)
        package_service = GitLabPackageService(self.group_rpath, self.gitlab)
        buildinfo_service = GitLabBuildInfoService(self.gitlab, cache_service)
        dependency_service = GitLabDependencyService(buildinfo_service)
        workspace_service = GitLabWorkspaceService(package_service)

        container_service = DockerContainerService()
        environment_service = GitLabEnvironmentService(package_service)
        vscode_editor_strategy = VSCodeEditorStrategy()

        self._services[CacheService] = cache_service
        self._services[PackageService] = package_service
        self._services[DependencyService] = dependency_service
        self._services[BuildInfoService] = buildinfo_service
        self._services[WorkspaceService] = workspace_service
        self._services[ContainerService] = container_service
        self._services[EnvironmentService] = environment_service

        self._editor_strategies = {"code": vscode_editor_strategy}

        if self.project_id:
            shared_issue_writer = GitLabIssueWriter(self.gitlab, self.project_id)
            storage_service = GitLabStorageService(shared_issue_writer)
            notify_service = GitLabNotifyService(shared_issue_writer)
            self._services[StorageService] = storage_service
            self._services[NotifyService] = notify_service
            logger.debug(
                "Registered GitLab storage and notification services with shared issue writer for project %s",
                self.project_id,
            )
        else:
            storage_service = FilesystemStorageService()
            notify_service = FilesystemNotifyService()
            self._services[StorageService] = storage_service
            self._services[NotifyService] = notify_service
            logger.debug("Registered filesystem storage and notification services for local execution")

    def obtain_ref(self, ref_type: Type[T]) -> T:
        if ref_type not in self._services:
            raise ReferenceNotFoundError(f"Service {ref_type.__name__} is not registered")

        return self._services[ref_type]

    def get_editor_strategy(self, editor_name: str) -> EditorStrategy:
        """
        Get an editor strategy by name.

        Args:
            editor_name: Name of the editor strategy

        Returns:
            EditorStrategy implementation

        Raises:
            ReferenceNotFoundError: If editor strategy is not found
        """
        if editor_name not in self._editor_strategies:
            raise ReferenceNotFoundError(f"Editor strategy '{editor_name}' is not registered")

        return self._editor_strategies[editor_name]

    def register_reference(self, reference_type: Type[T], implementation: T) -> None:
        """
        Register a service implementation for a given type.

        Args:
            reference_type: The abstract service type
            implementation: The concrete implementation instance
        """
        self._services[reference_type] = implementation
        logger.debug("Registered service %s", reference_type.__name__)
