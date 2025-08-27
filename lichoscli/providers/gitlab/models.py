"""GitLab model wrappers that implement the abstract interfaces."""

from typing import Optional
from gitlab.v4.objects import (
    Project as GitLabProject,
    MergeRequest as GitLabMergeRequest,
)
from gitlab.v4.objects import ProjectPipeline as GitLabPipeline, ProjectJob as GitLabJob
from gitlab.v4.objects import Group as GitLabGroup
from gitlab import GitlabError

from lichoscli.core.models import Project, MergeRequest, Pipeline, Job, Group


class GitLabProjectWrapper(Project):
    """Wrapper for GitLab Project objects."""

    def __init__(self, gitlab_project: GitLabProject):
        self._project = gitlab_project

    @property
    def id(self) -> str:
        return str(self._project.id)

    @property
    def name(self) -> str:
        return self._project.name

    @property
    def path_with_namespace(self) -> str:
        return self._project.path_with_namespace

    @property
    def web_url(self) -> str:
        return self._project.web_url

    @property
    def default_branch(self) -> str:
        return self._project.default_branch

    @property
    def ci_config_path(self) -> Optional[str]:
        return getattr(self._project, "ci_config_path", None)

    @property
    def archived(self) -> bool:
        return getattr(self._project, "archived", False)

    @property
    def gitlab_project(self) -> GitLabProject:
        """Access to underlying GitLab project for provider-specific operations."""
        return self._project


class GitLabMergeRequestWrapper(MergeRequest):
    """Wrapper for GitLab MergeRequest objects."""

    def __init__(self, gitlab_mr: GitLabMergeRequest):
        self._mr = gitlab_mr

    @property
    def id(self) -> str:
        return str(self._mr.id)

    @property
    def iid(self) -> str:
        return str(self._mr.iid)

    @property
    def source_branch(self) -> str:
        return self._mr.source_branch

    @property
    def target_branch(self) -> str:
        return self._mr.target_branch

    @property
    def web_url(self) -> str:
        return self._mr.web_url

    @property
    def state(self) -> str:
        return self._mr.state

    @property
    def gitlab_mr(self) -> GitLabMergeRequest:
        """Access to underlying GitLab MR for provider-specific operations."""
        return self._mr


class GitLabPipelineWrapper(Pipeline):
    """Wrapper for GitLab Pipeline objects."""

    def __init__(self, gitlab_pipeline: GitLabPipeline):
        self._pipeline = gitlab_pipeline

    @property
    def id(self) -> str:
        return str(self._pipeline.id)

    @property
    def status(self) -> str:
        return self._pipeline.status

    @property
    def ref(self) -> str:
        return self._pipeline.ref

    @property
    def web_url(self) -> str:
        return self._pipeline.web_url

    @property
    def gitlab_pipeline(self) -> GitLabPipeline:
        """Access to underlying GitLab pipeline for provider-specific operations."""
        return self._pipeline


class GitLabJobWrapper(Job):
    """Wrapper for GitLab Job objects."""

    def __init__(self, gitlab_job: GitLabJob, project: GitLabProject):
        self._job = gitlab_job
        self._project = project

    @property
    def id(self) -> str:
        return str(self._job.id)

    @property
    def name(self) -> str:
        return self._job.name

    @property
    def status(self) -> str:
        return self._job.status

    def get_trace(self) -> Optional[str]:
        """Get job execution log."""
        try:
            full_job = self._project.jobs.get(self._job.id)
            trace = full_job.trace()
            if trace:
                return (
                    trace.decode("utf-8", errors="replace")
                    if isinstance(trace, bytes)
                    else trace
                )
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

    @property
    def gitlab_job(self) -> GitLabJob:
        """Access to underlying GitLab job for provider-specific operations."""
        return self._job


class GitLabGroupWrapper(Group):
    """Wrapper for GitLab Group objects."""

    def __init__(self, gitlab_group: GitLabGroup):
        self._group = gitlab_group

    @property
    def id(self) -> str:
        return str(self._group.id)

    @property
    def name(self) -> str:
        return self._group.name

    @property
    def path(self) -> str:
        return self._group.path

    @property
    def full_path(self) -> str:
        return self._group.full_path

    @property
    def gitlab_group(self) -> GitLabGroup:
        """Access to underlying GitLab group for provider-specific operations."""
        return self._group
