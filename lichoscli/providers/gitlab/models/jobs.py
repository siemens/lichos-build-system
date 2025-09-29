"""GitLab Jobs collection wrapper."""

import logging
from typing import TYPE_CHECKING, List, Optional

from gitlab import GitlabError
from gitlab.v4.objects import ProjectPipeline as GitLabPipeline

from lichoscli.core.models import Job, Jobs

from .job import GitLabJob

if TYPE_CHECKING:
    from lichoscli.core.models import Pipeline

logger = logging.getLogger(__name__)


class GitLabJobs(Jobs):
    """Wrapper for GitLab Pipeline Jobs collection."""

    def __init__(self, gitlab_pipeline: GitLabPipeline, project, pipeline_ref: "Pipeline" = None):
        self._pipeline = gitlab_pipeline
        self._project = project
        self._ref_name = gitlab_pipeline.ref  # Store pipeline ref for job creation
        self._pipeline_ref = pipeline_ref

    def get_by_name(self, job_name: str) -> Optional[Job]:
        """Find a job by name in this pipeline."""
        try:
            jobs = self._pipeline.jobs.list(all=True)
            job = next((job for job in jobs if job.name == job_name), None)
            if job:
                return GitLabJob(
                    job,
                    self._project,
                    ref_name=self._ref_name,
                    pipeline_ref=self._pipeline_ref,
                )
            return None
        except GitlabError as e:
            logger.error(
                "Failed to get job %s for pipeline: %s",
                job_name,
                str(e),
            )
            return None

    def get_by_id(self, job_id: str) -> Optional[Job]:
        """Get a job by its ID."""
        try:
            job = self._project.jobs.get(job_id)
            return GitLabJob(
                job,
                self._project,
                ref_name=self._ref_name,
                pipeline_ref=self._pipeline_ref,
            )
        except GitlabError as e:
            logger.error(
                "Failed to get job %s: %s",
                job_id,
                str(e),
            )
            return None

    def list(self) -> List[Job]:
        """Get all jobs in this pipeline."""
        try:
            jobs = self._pipeline.jobs.list(all=True)
            return [
                GitLabJob(
                    job,
                    self._project,
                    ref_name=self._ref_name,
                    pipeline_ref=self._pipeline_ref,
                )
                for job in jobs
            ]
        except GitlabError as e:
            logger.error(
                "Failed to get jobs for pipeline: %s",
                str(e),
            )
            return []

    def extract_log_from_job(self, job_name: str) -> Optional[str]:
        """Extract log from a job by name."""
        job = self.get_by_name(job_name)
        if not job:
            return None

        return job.get_trace()
