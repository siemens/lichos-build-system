"""GitLab merge requests collection implementation."""

import logging
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.models import Job, MergeRequest, MergeRequests

from .job import GitLabJob
from .merge_request import GitLabMergeRequest

logger = logging.getLogger(__name__)


class GitLabMergeRequests(MergeRequests):
    """GitLab implementation of merge requests collection."""

    def __init__(self, gitlab_project):
        self._gitlab_project = gitlab_project

    def list(
        self,
        state: str = "opened",
        branch_name: Optional[str] = None,
        get_all: bool = False,
    ) -> list[MergeRequest]:
        """Get merge requests in this collection."""
        try:
            filters = {"state": state}
            if branch_name:
                filters["source_branch"] = branch_name
            if get_all:
                filters["all"] = get_all

            mrs = self._gitlab_project.mergerequests.list(**filters)
            logger.debug(
                "Found %d merge requests with filters: %s",
                len(mrs),
                filters,
            )
            return [GitLabMergeRequest(mr) for mr in mrs]
        except GitlabError as e:
            logger.error(
                "Failed to fetch merge requests: %s",
                str(e),
            )
            return []

    def get(self, mr_iid: str) -> Optional[MergeRequest]:
        """Get a specific merge request by IID."""
        try:
            mr = self._gitlab_project.mergerequests.get(mr_iid)
            return GitLabMergeRequest(mr)
        except GitlabError as e:
            logger.error(
                "Failed to fetch merge request %s: %s",
                mr_iid,
                str(e),
            )
            return None

    def get_job_by_name_from_mr(self, job_name: str, branch: Optional[str] = None) -> Optional[Job]:
        """Find the specified job in the latest merge request pipeline for the given branch."""
        try:
            # Get open merge requests for the branch
            mrs = self.list(state="opened", branch_name=branch)

            if not mrs:
                logger.debug(
                    "No open merge requests found for branch %s",
                    branch or "default",
                )
                return None

            # Use the first (most recent) merge request
            mr_partial = mrs[0]._mr
            logger.debug(
                "Found merge request #%s for branch %s",
                mr_partial.iid,
                mr_partial.source_branch,
            )

            # Get the full merge request object to access head_pipeline
            mr = self._gitlab_project.mergerequests.get(mr_partial.iid)

            # Get the head pipeline from the merge request
            head_pipeline = mr.head_pipeline
            if not head_pipeline:
                logger.debug("No head pipeline found for merge request #%s", mr.iid)
                return None

            # Get the full pipeline object
            pipeline = self._gitlab_project.pipelines.get(head_pipeline["id"])
            pipeline_jobs = pipeline.jobs.list(all=True)

            if not pipeline_jobs:
                logger.debug("No jobs found in merge request pipeline")
                return None

            job = next((j for j in pipeline_jobs if j.name == job_name), None)
            if job is None:
                logger.debug("Job %s not found in merge request pipeline", job_name)
            else:
                logger.debug("Found job %s in merge request #%s pipeline", job_name, mr.iid)

            return GitLabJob(job, self._gitlab_project) if job else None

        except GitlabError as e:
            logger.error("Error getting job from merge request: %s", str(e))
            return None

    def extract_log_from_job_mr(self, job_name: str, branch: Optional[str] = None) -> Optional[str]:
        """Extract log from a job in a merge request pipeline."""
        try:
            job = self.get_job_by_name_from_mr(job_name, branch)
            if not job:
                return None

            return job.get_trace()

        except GitlabError as e:
            logger.warning("Error extracting log from merge request job %s: %s", job_name, str(e))
            return None
