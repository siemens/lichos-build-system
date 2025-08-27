from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import tempfile
from .models import Project, MergeRequest, Pipeline, Job, Group


class PackageService(ABC):
    """Abstract interface for package management operations."""

    @abstractmethod
    def get_package(self, package_name: str) -> Optional[Project]:
        """Get a package by name."""

    @abstractmethod
    def get_all_packages(self) -> List[Project]:
        """Get all packages in the group."""

    @abstractmethod
    def create_package(
        self,
        name: str,
        branch: str,
        package_type: str,
        subgroup: str,
        access_level: str = "enabled",
    ) -> Optional[Project]:
        """Create a new package."""

    @abstractmethod
    def update_package(
        self,
        package_name: str,
        ci_config_path: Optional[str] = None,
        branch: Optional[str] = None,
        access_level: str = "enabled",
    ) -> Optional[Project]:
        """Update package configuration."""

    @abstractmethod
    def get_package_branch(self, package: Project, branch: str):
        """Get a specific branch from a package."""


class PipelineService(ABC):
    """Abstract interface for pipeline management operations."""

    @abstractmethod
    def get_latest_pipeline(
        self, package: Project, branch: str = None
    ) -> Optional[Pipeline]:
        """Get the latest pipeline for a package branch."""

    @abstractmethod
    def trigger_build(self, package: Project, branch_name: str = None) -> int:
        """Trigger a build for a package."""

    @abstractmethod
    def verify_builds_success(self, packages: List[Project]) -> bool:
        """Verify builds and tests for all packages."""

    @abstractmethod
    def get_job_by_name(self, package: Project, job_name: str) -> Optional[Job]:
        """Find a job by name in the latest pipeline."""

    @abstractmethod
    def get_job_by_id(self, package: Project, job_id: str) -> Optional[Job]:
        """Get a job by its ID."""

    @abstractmethod
    def extract_log_from_job(self, package: Project, job_name: str) -> Optional[str]:
        """Extract log from a job."""


class MergeRequestService(ABC):
    """Abstract interface for merge request operations."""

    @abstractmethod
    def get_merge_requests_for_package(
        self,
        package: Project,
        branch_name: str = None,
        state: str = "opened",
        get_all: bool = False,
    ) -> List[MergeRequest]:
        """Get merge requests for a package."""

    @abstractmethod
    def get_job_by_name_from_mr(
        self, package: Project, job_name: str, branch: str = None
    ) -> Optional[Job]:
        """Find a job by name in merge request pipeline."""

    @abstractmethod
    def extract_log_from_job_mr(
        self, package: Project, job_name: str, branch: str = None
    ) -> Optional[str]:
        """Extract log from a job in merge request pipeline."""


class ArtifactService(ABC):
    """Abstract interface for artifact management operations."""

    @abstractmethod
    def get_job_artifacts(
        self, package: Project, branch_name: str, job_name: str
    ) -> Optional[tempfile.TemporaryDirectory]:
        """Get job artifacts as a temporary directory."""

    @abstractmethod
    def get_artifacts_by_job_id(self, package: Project, job_id: str) -> Optional[bytes]:
        """Get artifacts by job ID."""

    @abstractmethod
    def get_artifacts_by_mr(
        self, package: Project, branch_name: str, job_name: str
    ) -> Optional[bytes]:
        """Get artifacts via merge request."""


class ForkService(ABC):
    """Abstract interface for forking operations."""

    @abstractmethod
    def fork_package(
        self, parent_package: Project, subgroup: Optional[str] = None
    ) -> Optional[Project]:
        """Fork a package to the current hierarchy with optional subgroup."""


class VariableService(ABC):
    """Abstract interface for variable management operations."""

    @abstractmethod
    def get_package_variables(self, package: Project) -> Dict[str, Any]:
        """Get package-level variables."""

    @abstractmethod
    def set_group_variable(
        self,
        group_path: str,
        key: str,
        value: str,
        masked: bool = False,
        protected: bool = False,
    ) -> bool:
        """Set a group-level variable."""


class GroupService(ABC):
    """Abstract interface for group management operations."""

    @abstractmethod
    def get_group(self, namespace_path: str) -> Optional[Group]:
        """Get a group by namespace path."""

    @abstractmethod
    def hierarchy_exists(self, target_path: str) -> bool:
        """Check if a hierarchy exists at the target path."""

    @abstractmethod
    def create_subgroup(self, subgroup_path: str) -> bool:
        """Create a subgroup."""
