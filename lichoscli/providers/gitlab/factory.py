"""GitLab service factory implementation."""
import logging
from typing import TYPE_CHECKING, Optional

from lichoscli.core.services import (
    BuildInfoService,
    CacheService,
    PackageService,
    PkgGroupDiscoveryService,
    RepoParserService,
    SourceCollectionService,
)
from lichoscli.core.services.commit_status import CommitStatusService
from lichoscli.core.services.dependency import DependencyService
from lichoscli.core.services.notify import NotifyService
from lichoscli.core.services.scheduler_service import SchedulerService
from lichoscli.core.services.storage import StorageService
from lichoscli.providers.docker import DockerContainerService
from lichoscli.core.handlers.lichos_anchor import LichosAnchorHandler
from lichoscli.providers.filesystem import FilesystemNotifyService
from lichoscli.providers.filesystem.cache_service import DiskCacheService
from lichoscli.providers.gitlab.client import GitLabClientFactory
from lichoscli.providers.gitlab.services.buildinfo_service import GitLabBuildInfoService
from lichoscli.providers.gitlab.services.commit_status_service import GitLabCommitStatusService
from lichoscli.providers.gitlab.services.dependency_service import GitLabDependencyService
from lichoscli.providers.gitlab.services.environment_service import GitLabEnvironmentService
from lichoscli.providers.gitlab.services.gitlab_issue_writer import GitLabIssueWriter
from lichoscli.providers.gitlab.services.notify_service import GitLabNotifyService
from lichoscli.providers.gitlab.services.package_service import GitLabPackageService
from lichoscli.providers.gitlab.services.pkg_group_discovery_service import GitLabPkgGroupDiscoveryService
from lichoscli.providers.gitlab.services.scheduler_service import GitLabSchedulerService
from lichoscli.providers.gitlab.services.storage_service import GitLabStorageService
from lichoscli.providers.gitlab.services.workspace_service import GitLabWorkspaceService
from lichoscli.ui.interfaces import UserInterface

if TYPE_CHECKING:
    from lichoscli.providers.gitlab.container import GitLabServiceContainer

logger = logging.getLogger(__name__)


class GitLabServiceFactory:
    """Factory for creating GitLab services with lazy initialization."""

    def __init__(self, container: "GitLabServiceContainer"):
        self.container = container
        self._shared_issue_writer: Optional[GitLabIssueWriter] = None

    def create_cache_service(self) -> DiskCacheService:
        # 60 seconds * 60 minutes * 24 hours = 1 day
        return DiskCacheService(default_ttl=60 * 60 * 24)

    def create_package_service(self) -> GitLabPackageService:
        # Note: self.container.gitlab will trigger lazy initialization of gitlab client
        if self.container.group_rpath is None:
            raise ValueError(
                "Package group (pkg-group) not found. Please specify --pkg-group or run from a git repository with a GitLab remote."
            )
        return GitLabPackageService(self.container.group_rpath, self.container.gitlab)

    def create_buildinfo_service(self) -> GitLabBuildInfoService:
        return GitLabBuildInfoService(self.container.gitlab, self.container.obtain_ref(CacheService))

    def create_dependency_service(self) -> GitLabDependencyService:
        return GitLabDependencyService(self.container.obtain_ref(BuildInfoService))

    def create_workspace_service(self) -> GitLabWorkspaceService:
        return GitLabWorkspaceService(self.container.obtain_ref(PackageService))

    def create_container_service(self) -> DockerContainerService:
        return DockerContainerService()

    def create_environment_service(self) -> GitLabEnvironmentService:
        return GitLabEnvironmentService(self.container.obtain_ref(PackageService))

    def create_repo_parser_service(self) -> RepoParserService:
        return RepoParserService()

    def create_source_collection_service(self) -> SourceCollectionService:
        return SourceCollectionService(self.container.obtain_ref(RepoParserService))

    def _get_issue_writer(self) -> GitLabIssueWriter:
        if not self._shared_issue_writer:
            self._shared_issue_writer = GitLabIssueWriter(self.container.gitlab, self.container.project_id)
        return self._shared_issue_writer

    def create_gitlab_storage_service(self) -> GitLabStorageService:
        return GitLabStorageService(self._get_issue_writer())

    def create_gitlab_notify_service(self) -> GitLabNotifyService:
        return GitLabNotifyService(self._get_issue_writer())

    def create_pkg_group_discovery_service(self) -> GitLabPkgGroupDiscoveryService:
        return GitLabPkgGroupDiscoveryService(
            self.container.gitlab,
            lambda host: GitLabClientFactory(host).create(),
        )

    def create_fs_notify_service(self) -> FilesystemNotifyService:
        ui = self.container.obtain_ref(UserInterface)
        return FilesystemNotifyService(ui.output)

    def create_commit_status_service(self) -> GitLabCommitStatusService:
        return GitLabCommitStatusService()

    def create_scheduler_service(self) -> GitLabSchedulerService:
        return GitLabSchedulerService(
            dependency_service=self.container.obtain_ref(DependencyService),
            storage_service=self.container.obtain_ref(StorageService),
            commit_status_service=self.container.obtain_ref(CommitStatusService),
            notify_service=self.container.obtain_ref(NotifyService),
        )

    def create_lichos_anchor_handler(self) -> LichosAnchorHandler:
        return LichosAnchorHandler()
