"""GitLab merge request service implementation."""

import logging
from typing import List, Optional

from gitlab import GitlabError

from lichoscli.core.services import MergeRequestService
from lichoscli.core.models import Project, MergeRequest, Job
from lichoscli.providers.gitlab.models import (
    GitLabProjectWrapper,
    GitLabMergeRequestWrapper,
    GitLabJobWrapper,
)

logger = logging.getLogger(__name__)


class GitLabMergeRequestService(MergeRequestService):
    """GitLab implementation of merge request management operations."""

    def __init__(self, gitlab):
        self.gitlab = gitlab

    def get_merge_requests_for_package(
        self,
        package: Project,
        branch_name: str = None,
        state: str = "opened",
        get_all: bool = False,
    ) -> List[MergeRequest]:
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        try:
            filters = {"state": state}
            if branch_name:
                filters["source_branch"] = branch_name
            if get_all:
                filters["all"] = get_all

            mrs = gitlab_pkg.mergerequests.list(**filters)
            logger.debug(
                "Found %d merge requests for package %s with filters: %s",
                len(mrs),
                package.name,
                filters,
            )
            return [GitLabMergeRequestWrapper(mr) for mr in mrs]
        except GitlabError as e:
            logger.error(
                "Failed to fetch merge requests for package %s: %s",
                package.name,
                str(e),
            )
            return []

    def get_job_by_name_from_mr(
        self, package: Project, job_name: str, branch: str = None
    ) -> Optional[Job]:
        """Find the specified job in the latest merge request pipeline for the given branch."""
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        try:
            # Get open merge requests for the branch
            mrs = self.get_merge_requests_for_package(
                package, branch_name=branch, state="opened"
            )

            if not mrs:
                logger.debug(
                    "No open merge requests found for branch %s in package %s",
                    branch or "default",
                    package.name,
                )
                return None

            # Use the first (most recent) merge request
            mr_partial = mrs[0].gitlab_mr
            logger.debug(
                "Found merge request #%s for branch %s",
                mr_partial.iid,
                mr_partial.source_branch,
            )

            # Get the full merge request object to access head_pipeline
            mr = gitlab_pkg.mergerequests.get(mr_partial.iid)

            # Get the head pipeline from the merge request
            head_pipeline = mr.head_pipeline
            if not head_pipeline:
                logger.debug("No head pipeline found for merge request #%s", mr.iid)
                return None

            # Get the full pipeline object
            pipeline = gitlab_pkg.pipelines.get(head_pipeline["id"])
            pipeline_jobs = pipeline.jobs.list(all=True)

            if not pipeline_jobs:
                logger.debug("No jobs found in merge request pipeline")
                return None

            job = next((j for j in pipeline_jobs if j.name == job_name), None)
            if job is None:
                logger.debug("Job %s not found in merge request pipeline", job_name)
            else:
                logger.debug(
                    "Found job %s in merge request #%s pipeline", job_name, mr.iid
                )

            return GitLabJobWrapper(job, gitlab_pkg) if job else None

        except GitlabError as e:
            logger.error("Error getting job from merge request: %s", str(e))
            return None

    def extract_log_from_job_mr(
        self, package: Project, job_name: str, branch: str = None
    ) -> Optional[str]:
        """Extract log from a job in a merge request pipeline."""
        try:
            job = self.get_job_by_name_from_mr(package, job_name, branch)
            if not job:
                return None

            return job.get_trace()

        except GitlabError as e:
            logger.warning(
                "Error extracting log from merge request job %s: %s", job_name, str(e)
            )
            return None
