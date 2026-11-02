# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Jobs collection wrapper."""

import logging
from typing import TYPE_CHECKING, Optional

from gitlab import GitlabError
from gitlab.v4.objects import ProjectPipeline as GitLabPipeline

from lichoscli.core.models import Job, Jobs
from lichoscli.core.models.dag import WorkspaceStatus
from lichoscli.core.models.pipeline_status import PipelineStatus
from lichoscli.utils.constants import CI_WORKSPACE_JOB_NAME

from .job import GitLabJob

if TYPE_CHECKING:
    from lichoscli.core.models import Pipeline

logger = logging.getLogger(__name__)


class GitLabJobs(Jobs):
    """Wrapper for GitLab Pipeline Jobs collection."""

    def __init__(self, gitlab_pipeline: GitLabPipeline, project, pipeline_ref: Optional["Pipeline"] = None):
        self._pipeline = gitlab_pipeline
        self._project = project
        self._ref_name = gitlab_pipeline.ref  # Store pipeline ref for job creation
        self._pipeline_ref = pipeline_ref
        self._commit_statuses = None

    def get_by_name(self, job_name: str) -> Optional[Job]:
        """Find a job by name in this pipeline."""
        try:
            jobs = self._pipeline.jobs.list(all=True)
            job = next((j for j in jobs if j.name == job_name or j.name.startswith(f"{job_name}")), None)
            if job:
                gitlab_job = self._project.jobs.get(job.id)
                return GitLabJob(gitlab_job, self._project, ref_name=self._ref_name, pipeline_ref=self._pipeline_ref)
            return None
        except GitlabError as e:
            logger.error("Failed to get job %s for pipeline: %s", job_name, str(e))
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

    def list(self) -> list[Job]:
        """Get all jobs in this pipeline."""
        try:
            jobs = self._pipeline.jobs.list(all=True)
            return [
                GitLabJob(
                    self._project.jobs.get(job.id),
                    self._project,
                    ref_name=self._ref_name,
                    pipeline_ref=self._pipeline_ref,
                )
                for job in jobs
            ]
        except GitlabError as e:
            logger.error("Failed to get jobs for pipeline: %s", str(e))
            return []

    def has_any_failed(self) -> bool:
        """Return True if any job or bridge (trigger) in this pipeline has a non-success final status."""
        _non_success = PipelineStatus.non_success_final_values()
        try:
            jobs = self._pipeline.jobs.list(all=True)
            if any(j.status in _non_success for j in jobs):
                return True
            bridges = self._pipeline.bridges.list(all=True)
            return any(b.status in _non_success for b in bridges)
        except GitlabError as e:
            logger.error("Failed to check job statuses for pipeline: %s", str(e))
            return False

    def _get_commit_statuses(self) -> list:
        if self._commit_statuses is None:
            try:
                self._commit_statuses = self._project.commits.get(self._pipeline.sha, lazy=True).statuses.list(
                    pipeline_id=self._pipeline.id, per_page=100, get_all=True
                )
            except GitlabError as e:
                logger.error("Failed to get commit statuses for pipeline: %s", str(e))
                self._commit_statuses = []
        return self._commit_statuses

    def workspace_status(self) -> Optional[WorkspaceStatus]:
        """The workspace-scheduling status the scheduler posted onto this pipeline, if any."""
        for s in self._get_commit_statuses():
            if s.name == CI_WORKSPACE_JOB_NAME and s.status in {w.value for w in WorkspaceStatus}:
                return WorkspaceStatus(s.status)
        return None

    def aggregate_status(self) -> Optional[PipelineStatus]:
        """Combined status of the pipeline's commit statuses, without the workspace-scheduling one."""
        statuses = {
            s.status
            for s in self._get_commit_statuses()
            if s.name != CI_WORKSPACE_JOB_NAME and not (getattr(s, "allow_failure", False) and s.status == "failed")
        }
        if not statuses:
            return None
        if "running" in statuses:
            return PipelineStatus.RUNNING
        if statuses & PipelineStatus.in_progress_values() - {"manual"}:
            return PipelineStatus.PENDING
        if "failed" in statuses:
            return PipelineStatus.FAILED
        if statuses & {"canceled", "canceling"}:
            return PipelineStatus.CANCELED
        if "success" in statuses:
            return PipelineStatus.SUCCESS
        return PipelineStatus.MANUAL if "manual" in statuses else PipelineStatus.SKIPPED

    def extract_log_from_job(self, job_name: str) -> Optional[str]:
        """Extract log from a job by name."""
        job = self.get_by_name(job_name)
        if not job:
            return None

        return job.get_trace()
