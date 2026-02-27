# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Pipeline model wrapper."""

from typing import TYPE_CHECKING, Optional

from gitlab import GitlabError
from gitlab.v4.objects import ProjectPipeline as GitLabProjectPipeline

from lichoscli.core.models import Jobs, Pipeline
from lichoscli.core.models.pipeline_status import PipelineStatus

from .jobs import GitLabJobs
from .user import GitLabUser

if TYPE_CHECKING:
    from lichoscli.core.models import Project, User


class GitLabPipeline(Pipeline):
    """Wrapper for GitLab Pipeline objects."""

    def __init__(self, gitlab_pipeline: GitLabProjectPipeline, project: "Project" = None):
        self._pipeline = gitlab_pipeline
        self._project_ref = project  # Core project reference
        self._jobs: Optional[Jobs] = None

    @property
    def id(self) -> int:
        return self._pipeline.get_id()

    @property
    def status(self) -> PipelineStatus:
        """Pipeline status as enum value."""
        status_str = self._pipeline.status
        if status_str is None:
            status_str = "created"
        return PipelineStatus.from_string(status_str)

    @property
    def ref(self) -> str:
        return self._pipeline.ref

    @property
    def web_url(self) -> str:
        return self._pipeline.web_url

    @property
    def updated_at(self) -> str:
        return self._pipeline.updated_at

    @property
    def sha(self) -> str:
        return self._pipeline.sha

    @property
    def source(self) -> str:
        return self._pipeline.source

    @property
    def user(self) -> Optional["User"]:
        """User who triggered the pipeline."""
        gitlab_user = getattr(self._pipeline, "user", None)
        if gitlab_user is None:
            return None
        return GitLabUser(gitlab_user)

    @property
    def project(self) -> "Project":
        """Parent project of this pipeline."""
        if self._project_ref is None:
            raise ValueError("Pipeline project reference not set")
        return self._project_ref

    @property
    def jobs(self) -> Jobs:
        """Access to pipeline jobs collection."""
        if self._jobs is None:
            # Get the underlying GitLab project for jobs wrapper
            gitlab_project = getattr(self._project_ref, "_project", None)
            self._jobs = GitLabJobs(self._pipeline, gitlab_project, pipeline_ref=self)
        return self._jobs

    def retry(self) -> bool:
        """Retry the pipeline."""
        try:
            self._pipeline.retry()
            return True
        except GitlabError:
            return False

    def cancel(self) -> bool:
        """Cancel the pipeline."""
        try:
            self._pipeline.cancel()
            return True
        except GitlabError:
            return False

    @property
    def gitlab_pipeline(self) -> GitLabProjectPipeline:
        """Access to underlying GitLab pipeline for provider-specific operations."""
        return self._pipeline
