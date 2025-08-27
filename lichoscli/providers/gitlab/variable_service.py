"""GitLab variable service implementation."""

import logging
from typing import Dict, Any

from gitlab import GitlabError

from lichoscli.core.services import VariableService
from lichoscli.core.models import Project
from lichoscli.providers.gitlab.models import GitLabProjectWrapper

logger = logging.getLogger(__name__)


class GitLabVariableService(VariableService):
    """GitLab implementation of variable management operations."""

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab

    def get_package_variables(self, package: Project) -> Dict[str, Any]:
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        try:
            variables = gitlab_pkg.variables.list(all=True)
            variables_dict = {}
            for v in variables:
                variables_dict[v.key] = v.value
            return variables_dict
        except GitlabError as e:
            if e.response_code == 403:
                logger.warning(
                    "No access to package variables for %s (403 Forbidden). Using empty variables.",
                    package.name,
                )
                return {}
            logger.error("Failed to get package variables for %s: %s", package.name, e)
            raise

    def set_group_variable(
        self,
        group_path: str,
        key: str,
        value: str,
        masked: bool = False,
        protected: bool = False,
    ) -> bool:
        """Set a group-level variable."""
        try:
            # Import here to avoid circular imports
            from .group_service import GitLabGroupService

            group_service = GitLabGroupService(self.group_rpath, self.gitlab)
            group = group_service.get_group(group_path)
        except GitlabError as e:
            logger.error("Failed to get group '%s': %s", group_path, str(e))
            return False

        if not group:
            logger.error("Group '%s' not found", group_path)
            return False

        gitlab_group = group.gitlab_group
        variable_data = {
            "key": key,
            "value": value,
            "masked": masked,
            "protected": protected,
        }
        try:
            existing_var = gitlab_group.variables.get(key)
            if existing_var:
                gitlab_group.variables.update(key, variable_data)
                logger.info(
                    "Updated group variable '%s' in group '%s'", key, group_path
                )
            else:
                gitlab_group.variables.create(variable_data)
                logger.info(
                    "Created group variable '%s' in group '%s'", key, group_path
                )
        except GitlabError as get_error:
            if get_error.response_code == 404:
                gitlab_group.variables.create(variable_data)
                logger.info(
                    "Created group variable '%s' in group '%s'", key, group_path
                )
            else:
                raise
        return True
