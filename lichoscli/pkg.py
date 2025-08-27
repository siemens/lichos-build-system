"""
Modular PkgGroupHandler that delegates to specialized services.
This maintains backward compatibility while providing a cleaner architecture.
"""

import logging
import tempfile
from typing import Optional, List

from gitlab.v4.objects import Project
from lichoscli.providers.gitlab.models import GitLabProjectWrapper
from lichoscli.providers.gitlab.provider import GitLabProvider

logger = logging.getLogger(__name__)


class PkgGroupHandler:
    """
    Backward-compatible package group handler that delegates to modular services.

    This class maintains the same public interface as the original PkgGroupHandler
    but internally uses the new modular service architecture.
    """

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab
        self.group_id = gitlab.groups.get(group_rpath).id

        # Initialize the GitLab provider with all services
        self._provider = GitLabProvider(group_rpath, gitlab)

        # Keep reference to individual services for easier access
        self._package_service = self._provider.package_service
        self._pipeline_service = self._provider.pipeline_service
        self._mr_service = self._provider.merge_request_service
        self._artifact_service = self._provider.artifact_service
        self._fork_service = self._provider.fork_service
        self._variable_service = self._provider.variable_service
        self._group_service = self._provider.group_service

    def get_package(self, package_name: str) -> Optional[Project]:
        """Get a package by name, returning the underlying GitLab project for compatibility."""
        wrapper = self._package_service.get_package(package_name)
        return wrapper.gitlab_project if wrapper else None

    def get_all_packages(self) -> List[Project]:
        """Get all packages, returning underlying GitLab projects for compatibility."""
        wrappers = self._package_service.get_all_packages()
        return [wrapper.gitlab_project for wrapper in wrappers]

    def add_package(
        self,
        package_name: str,
        branch: str,
        package_type: str,
        subgroup: str,
        access_level: str = "enabled",
    ):
        """Create a new package."""
        wrapper = self._package_service.create_package(
            package_name, branch, package_type, subgroup, access_level
        )
        return wrapper.gitlab_project if wrapper else None

    def update_package(
        self,
        package_name: str,
        ci_config_path: Optional[str] = None,
        branch: Optional[str] = None,
        access_level: str = "enabled",
    ):
        """Update package configuration."""
        wrapper = self._package_service.update_package(
            package_name, ci_config_path, branch, access_level
        )
        return wrapper.gitlab_project if wrapper else None

    def get_latest_pipeline(self, package: Project, branch: str = None):
        """Get the latest pipeline for a package branch."""

        wrapper = GitLabProjectWrapper(package)
        pipeline_wrapper = self._pipeline_service.get_latest_pipeline(wrapper, branch)
        return pipeline_wrapper.gitlab_pipeline if pipeline_wrapper else None

    def trigger_package_build(self, package: Project, branch_name=None):
        """Trigger a build for a package."""

        wrapper = GitLabProjectWrapper(package)
        return self._pipeline_service.trigger_build(wrapper, branch_name)

    def verify_builds_success(self, packages: List[Project]) -> bool:
        """Verify builds and tests for all packages."""

        wrappers = [GitLabProjectWrapper(pkg) for pkg in packages]
        return self._pipeline_service.verify_builds_success(wrappers)

    def get_job_by_name(self, pkg: Project, jobname: str):
        """Find the specified job in the latest pipeline."""

        wrapper = GitLabProjectWrapper(pkg)
        job_wrapper = self._pipeline_service.get_job_by_name(wrapper, jobname)
        return job_wrapper.gitlab_job if job_wrapper else None

    def get_job_by_id(self, pkg: Project, job_id: int):
        """Refresh a job to get its current status from GitLab."""

        wrapper = GitLabProjectWrapper(pkg)
        job_wrapper = self._pipeline_service.get_job_by_id(wrapper, str(job_id))
        return job_wrapper.gitlab_job if job_wrapper else None

    def extract_log_from_job(self, package: Project, job_name: str) -> Optional[str]:
        """Extract log from a job."""

        wrapper = GitLabProjectWrapper(package)
        return self._pipeline_service.extract_log_from_job(wrapper, job_name)


    # Merge Request Methods
    def get_merge_requests_for_package(
        self,
        package: Project,
        branch_name: str = None,
        state: str = "opened",
        get_all: bool = False,
    ) -> List:
        """Get merge requests for a package."""

        wrapper = GitLabProjectWrapper(package)
        mr_wrappers = self._mr_service.get_merge_requests_for_package(
            wrapper, branch_name, state, get_all
        )
        return [mr_wrapper.gitlab_mr for mr_wrapper in mr_wrappers]


    def get_job_by_name_from_mr(self, pkg: Project, jobname: str, branch: str = None):
        """Find the specified job in the latest merge request pipeline for the given branch."""

        wrapper = GitLabProjectWrapper(pkg)
        job_wrapper = self._mr_service.get_job_by_name_from_mr(wrapper, jobname, branch)
        return job_wrapper.gitlab_job if job_wrapper else None

    def extract_log_from_job_mr(
        self, package: Project, job_name: str, branch: str = None
    ) -> Optional[str]:
        """Extract log from a job in a merge request pipeline."""

        wrapper = GitLabProjectWrapper(package)
        return self._mr_service.extract_log_from_job_mr(wrapper, job_name, branch)

    # Artifact Methods
    def get_job_artifacts(
        self, package: Project, branch_name: str, job_name: str
    ) -> tempfile.TemporaryDirectory:
        """Get job artifacts as a temporary directory."""

        wrapper = GitLabProjectWrapper(package)
        return self._artifact_service.get_job_artifacts(wrapper, branch_name, job_name)


    # Fork Methods
    def fork_package(
        self, parent_package: Project, subgroup: Optional[str] = None
    ) -> Optional[Project]:
        """Fork a package to the current hierarchy with optional subgroup."""

        wrapper = GitLabProjectWrapper(parent_package)
        forked_wrapper = self._fork_service.fork_package(wrapper, subgroup)
        return forked_wrapper.gitlab_project if forked_wrapper else None

    # Variable Methods
    def get_package_variables(self, package: Project):
        """Get package-level variables."""

        wrapper = GitLabProjectWrapper(package)
        return self._variable_service.get_package_variables(wrapper)

    # Group Methods
    def get_group(self, namespace_path: str):
        """Get a group by namespace path."""
        group_wrapper = self._group_service.get_group(namespace_path)
        return group_wrapper.gitlab_group if group_wrapper else None

    def hierarchy_exists(self, target_path: str) -> bool:
        """Check if a hierarchy exists at the target path."""
        return self._group_service.hierarchy_exists(target_path)

    # Utility Methods
    def pretty_format_ci_path(self, package: Project):
        """Format CI path for display."""

        wrapper = GitLabProjectWrapper(package)
        return self._provider.pretty_format_ci_path(wrapper)
