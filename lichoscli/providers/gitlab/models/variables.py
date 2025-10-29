"""GitLab Variables collection wrapper."""

import builtins
import logging
from typing import Optional

import requests
from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProject

from lichoscli.core.models import Variable, Variables

from .variable import GitLabVariable

logger = logging.getLogger(__name__)


class GitLabVariables(Variables):
    """Wrapper for GitLab Project Variables collection."""

    def __init__(self, gitlab_project: GitLabProject):
        self._project = gitlab_project

    def list(self) -> list[Variable]:
        """Get all variables in this collection, including inherited ones from parent groups."""
        variables = []
        try:
            project_vars = [GitLabVariable(var, inherited=False) for var in self._project.variables.list(all=True)]
            variables.extend(project_vars)
        except GitlabError as e:
            logger.debug("Failed to fetch project variables: %s", str(e))
            return variables

        try:
            inherited_vars = self._get_inherited_variables()
            variables.extend(inherited_vars)
        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.warning("Failed to fetch inherited variables: %s", str(e))

        return variables

    def _get_inherited_variables(self) -> builtins.list[Variable]:
        """Get variables inherited from parent groups."""
        inherited_vars = []
        project_var_keys = {var.key for var in self._project.variables.list(all=True)}

        try:
            namespace = getattr(self._project, "namespace", {})
            if not namespace or namespace.get("kind") != "group":
                return inherited_vars

            gitlab = self._project.manager.gitlab
            current_group_id = namespace.get("id")

            if not current_group_id:
                return inherited_vars

            self._collect_group_variables(gitlab, current_group_id, project_var_keys, inherited_vars)

        except GitlabError as e:
            logger.debug("Error getting inherited variables: %s", str(e))

        return inherited_vars

    def _collect_group_variables(self, gitlab, group_id, project_var_keys, inherited_vars):
        """Recursively collect variables from a group and its parents."""
        try:
            group = gitlab.groups.get(group_id)

            group_variables = group.variables.list(all=True)
            for var in group_variables:
                if var.key not in project_var_keys and not any(iv.key == var.key for iv in inherited_vars):
                    inherited_vars.append(GitLabVariable(var, inherited=True))

            if hasattr(group, "parent_id") and group.parent_id:
                self._collect_group_variables(gitlab, group.parent_id, project_var_keys, inherited_vars)

        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.debug("Could not access group %s: %s", group_id, str(e))

    def get(self, key: str) -> Optional[Variable]:
        """Get a specific variable by key."""
        try:
            var = self._project.variables.get(key)
            return GitLabVariable(var, inherited=False)
        except (GitlabError, requests.exceptions.RequestException):
            return None

    def create(self, key: str, value: str, **kwargs) -> Variable:
        """Create a new variable with the given key and value."""
        var_data = {"key": key, "value": value}
        var_data.update(kwargs)
        var = self._project.variables.create(var_data)
        return GitLabVariable(var, inherited=False)

    def update(self, key: str, value: str, **kwargs) -> Variable:
        """Update an existing variable or create if it doesn't exist."""
        var_data = {"key": key, "value": value}
        var_data.update(kwargs)

        try:
            # Try to update existing variable
            var = self._project.variables.get(key)
            for k, v in var_data.items():
                if hasattr(var, k):
                    setattr(var, k, v)
            var.save()
            return GitLabVariable(var, inherited=False)
        except GitlabError:
            var = self._project.variables.create(var_data)
            return GitLabVariable(var, inherited=False)

    def delete(self, key: str) -> bool:
        """Delete a variable by key."""
        try:
            var = self._project.variables.get(key)
            var.delete()
            return True
        except GitlabError:
            return False

    def exists(self, key: str) -> bool:
        """Check if a variable exists by key."""
        try:
            self._project.variables.get(key)
            return True
        except GitlabError:
            return False
