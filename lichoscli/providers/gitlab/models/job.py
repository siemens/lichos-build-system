# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Job model wrapper."""

from typing import TYPE_CHECKING, Optional

from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProject
from gitlab.v4.objects import ProjectJob as GitLabJobModel

from lichoscli.core.models import Job

from .artifacts import GitLabArtifacts

if TYPE_CHECKING:
    from lichoscli.core.models import Pipeline


class GitLabJob(Job):
    """Wrapper for GitLab Job objects."""

    def __init__(
        self,
        gitlab_job: GitLabJobModel,
        project: GitLabProject,
        ref_name: str | None = None,
        pipeline_ref: "Pipeline | None" = None,
    ):
        self._job = gitlab_job
        self._project = project
        self._ref_name = ref_name
        self._pipeline_ref = pipeline_ref

    @property
    def id(self) -> str:
        return str(self._job.id)

    @property
    def name(self) -> str:
        return self._job.name

    @property
    def status(self) -> str:
        return self._job.status

    @property
    def web_url(self) -> str:
        return self._job.web_url

    @property
    def stage(self) -> str:
        return self._job.stage

    @property
    def started_at(self) -> Optional[str]:
        return self._job.started_at

    @property
    def finished_at(self) -> Optional[str]:
        return self._job.finished_at

    @property
    def pipeline(self) -> "Pipeline":
        """Parent pipeline of this job."""
        if self._pipeline_ref is None:
            raise ValueError("Job pipeline reference not set")
        return self._pipeline_ref

    @property
    def artifacts(self) -> "GitLabArtifacts":
        """Job artifacts collection."""

        # Use ref_name if available, otherwise try to get it from the project's default branch
        ref_name = self._ref_name or self._project.default_branch
        return GitLabArtifacts(self._project, self.name, ref_name, job_id=self.id)

    def get_trace(self) -> Optional[str]:
        """Get job execution log."""
        try:
            full_job = self._project.jobs.get(self._job.id)
            trace = full_job.trace()
            if trace:
                return trace.decode("utf-8", errors="replace") if isinstance(trace, bytes) else trace
            return None
        except GitlabError:
            return None

    def get_artifacts(self) -> Optional[bytes]:
        """Download job artifacts."""
        try:
            if not (job := self._project.jobs.get(self._job.id)):
                return None
            return job.artifacts()
        except GitlabError:
            return None

    def retry(self) -> bool:
        """Retry the job."""
        try:
            full_job = self._project.jobs.get(self._job.id)
            full_job.retry()
            return True
        except GitlabError:
            return False

    def cancel(self) -> bool:
        """Cancel the job."""
        try:
            full_job = self._project.jobs.get(self._job.id)
            full_job.cancel()
            return True
        except GitlabError:
            return False
