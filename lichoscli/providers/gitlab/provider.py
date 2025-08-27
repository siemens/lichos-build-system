"""GitLab provider factory that creates and manages all services."""

import logging
from lichoscli.utils import CIConfigUtils, CI_PKG
from lichoscli.core.models import Project

from .package_service import GitLabPackageService
from .pipeline_service import GitLabPipelineService
from .merge_request_service import GitLabMergeRequestService
from .artifact_service import GitLabArtifactService
from .fork_service import GitLabForkService
from .variable_service import GitLabVariableService
from .group_service import GitLabGroupService

logger = logging.getLogger(__name__)


class GitLabProvider:
    """GitLab provider that aggregates all GitLab services."""

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab

        # Initialize all services
        self.package_service = GitLabPackageService(group_rpath, gitlab)
        self.pipeline_service = GitLabPipelineService(gitlab)
        self.merge_request_service = GitLabMergeRequestService(gitlab)
        self.artifact_service = GitLabArtifactService(gitlab)
        self.fork_service = GitLabForkService(group_rpath, gitlab)
        self.variable_service = GitLabVariableService(group_rpath, gitlab)
        self.group_service = GitLabGroupService(group_rpath, gitlab)

    def pretty_format_ci_path(self, package: Project):
        """Format CI path for display - kept here for backward compatibility."""
        result = package.ci_config_path
        if not package.ci_config_path or package.ci_config_path == ".gitlab-ci.yml":
            result = "local"
        else:
            parsed = CIConfigUtils.parse_ci_config_path(package.ci_config_path)
            if parsed:
                group_matches = parsed.group == self.group_rpath
                parent_match = False
                if not group_matches:
                    p = self.package_service.get_package(CI_PKG)
                    if p and hasattr(p.gitlab_project, "forked_from_project"):
                        if (
                            p.gitlab_project.forked_from_project["namespace"][
                                "full_path"
                            ]
                            == parsed.group
                        ):
                            group_matches = True
                            parent_match = True
                if parsed and group_matches and parsed.pkg == CI_PKG:
                    result = parsed.name
                    if parent_match:
                        result += "*"
                    if parsed.branch:
                        result += ":" + parsed.branch

        logger.debug("%s: %s -> %s", package.name, package.ci_config_path, result)
        return result
