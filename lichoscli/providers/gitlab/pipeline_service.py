"""GitLab pipeline service implementation."""

import logging
from typing import Optional, List

from gitlab import GitlabError

from lichoscli.core.services import PipelineService
from lichoscli.core.models import Project, Pipeline, Job
from lichoscli.providers.gitlab.models import (
    GitLabProjectWrapper,
    GitLabPipelineWrapper,
    GitLabJobWrapper,
)
from lichoscli.utils import REQUIRED_PACKAGES
from .merge_request_service import GitLabMergeRequestService

logger = logging.getLogger(__name__)


class GitLabPipelineService(PipelineService):
    """GitLab implementation of pipeline management operations."""

    def __init__(self, gitlab):
        self.gitlab = gitlab

    def get_latest_pipeline(
        self, package: Project, branch: str = None
    ) -> Optional[Pipeline]:
        """Get the latest pipeline for a package branch."""
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        target_branch = branch if branch else gitlab_pkg.default_branch

        try:
            pipelines = gitlab_pkg.pipelines.list(
                ref=target_branch, per_page=1, order_by="id", sort="desc", get_all=False
            )
            if pipelines:
                return GitLabPipelineWrapper(pipelines[0])
            return None
        except GitlabError as e:
            logger.error(
                "Failed to get pipeline for %s on branch %s: %s",
                package.name,
                target_branch,
                str(e),
            )
            return None

    def trigger_build(self, package: Project, branch_name: str = None) -> int:
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        if branch_name is None:
            branch_name = gitlab_pkg.default_branch

        mr_info = None
        if branch_name != gitlab_pkg.default_branch:
            try:
                mr_service = GitLabMergeRequestService(self.gitlab)
                mrs = mr_service.get_merge_requests_for_package(
                    package, branch_name=branch_name, state="opened"
                )
                if mrs:
                    mr_info = mrs[0].gitlab_mr
                    logger.debug(
                        "Found merge request %s for branch %s", mr_info.iid, branch_name
                    )
            except GitlabError as e:
                logger.debug(
                    "Error checking for merge request on branch %s: %s",
                    branch_name,
                    str(e),
                )

        try:
            if mr_info:
                mr_info.pipelines.create({"ref": branch_name})
                print(
                    "Successfully triggered build for {} on MR !{} (branch {}): {}".format(
                        package.name, mr_info.iid, branch_name, mr_info.web_url
                    )
                )
                return 0
            else:
                gitlab_pkg.pipelines.create({"ref": branch_name})
                print(
                    "Successfully triggered build for {} on branch {}: {}/-/pipelines".format(
                        package.name, branch_name, gitlab_pkg.web_url
                    )
                )
                return 0

        except GitlabError as e:
            logger.error(
                "Failed to trigger build for %s on branch %s: %s",
                package.name,
                branch_name,
                str(e),
            )
            return 1

    def verify_builds_success(self, packages: List[Project]) -> bool:
        """Verify builds and tests for all packages."""
        logger.info("Verifying builds and tests for all packages")

        failed_packages = []

        for package in packages:
            if package.name in REQUIRED_PACKAGES:
                logger.debug("Skipping package: %s", package.name)
                continue
            logger.debug("Checking build status for package: %s", package.name)

            pipeline = self.get_latest_pipeline(package)

            if not pipeline:
                logger.warning("No pipeline found for package: %s", package.name)
                failed_packages.append(package.name)
                continue

            if pipeline.status != "success":
                logger.error(
                    "Pipeline failed for package %s with status: %s",
                    package.name,
                    pipeline.status,
                )
                failed_packages.append(package.name)
                continue

            logger.debug("Package %s build status: %s", package.name, pipeline.status)

        if failed_packages:
            logger.error(
                "The following packages have failed builds: %s",
                ", ".join(failed_packages),
            )
            return False

        logger.info("All package builds and tests passed successfully")
        return True

    def get_job_by_name(self, package: Project, job_name: str) -> Optional[Job]:
        """Find the specified job in the latest pipeline."""
        latest_pipeline = self.get_latest_pipeline(package)
        if latest_pipeline is None:
            logger.error(
                "No pipeline found for job %s in package %s.", job_name, package.name
            )
            return None

        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        gitlab_pipeline = latest_pipeline.gitlab_pipeline

        pipeline_jobs = gitlab_pipeline.jobs.list(all=True)
        if not pipeline_jobs:
            logger.error(
                "No jobs found in the latest pipeline for package %s.", package.name
            )
            return None

        job = next((j for j in pipeline_jobs if j.name == job_name), None)
        if job is None:
            logger.error("Job %s not found in package %s.", job_name, package.name)
            return None

        return GitLabJobWrapper(job, gitlab_pkg)

    def get_job_by_id(self, package: Project, job_id: str) -> Optional[Job]:
        """Refresh a job to get its current status from GitLab."""
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        try:
            job = self.gitlab.projects.get(gitlab_pkg.id).jobs.get(job_id)
            return GitLabJobWrapper(job, gitlab_pkg)
        except GitlabError as e:
            logger.error("Error getting a job with ID %s: %s", job_id, e)
            return None

    def extract_log_from_job(self, package: Project, job_name: str) -> Optional[str]:
        try:
            job = self.get_job_by_name(package, job_name)
            if not job:
                logger.warning(
                    "Job %s not found for package %s", job_name, package.name
                )
                return None

            return job.get_trace()

        except GitlabError as e:
            logger.warning("Error extracting log from job %s: %s", job_name, str(e))
            return None
