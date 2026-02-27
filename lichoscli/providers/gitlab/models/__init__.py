# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab model wrappers that implement the abstract interfaces."""

from .artifacts import GitLabArtifacts
from .job import GitLabJob
from .jobs import GitLabJobs
from .merge_request import GitLabMergeRequest
from .merge_requests import GitLabMergeRequests
from .pipeline import GitLabPipeline
from .pipelines import GitLabPipelines
from .project import GitLabProject
from .projects import GitLabProjects
from .tag import GitLabTag
from .tags import GitLabTags
from .user import GitLabUser
from .variable import GitLabVariable
from .variables import GitLabVariables
from .workspace import GitLabWorkspace

__all__ = [
    "GitLabProject",
    "GitLabProjects",
    "GitLabMergeRequest",
    "GitLabMergeRequests",
    "GitLabPipeline",
    "GitLabJob",
    "GitLabJobs",
    "GitLabVariable",
    "GitLabTag",
    "GitLabVariables",
    "GitLabTags",
    "GitLabPipelines",
    "GitLabArtifacts",
    "GitLabWorkspace",
    "GitLabUser",
]
