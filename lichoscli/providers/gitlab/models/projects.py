# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Projects collection wrapper."""

import logging
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.models import Project, Projects

from .project import GitLabProject

logger = logging.getLogger(__name__)


class GitLabProjects(Projects):
    """Wrapper for GitLab Group Projects collection."""

    def __init__(self, group_path: str, gitlab_client):
        self._group_path = group_path
        self._gitlab = gitlab_client
        self._group = None
        self._cache = {}

    @property
    def path(self) -> str:
        """Get the group path of this project collection."""
        return self._group_path

    @property
    def group(self):
        """Lazy load the GitLab group."""
        if self._group is None:
            self._group = self._gitlab.groups.get(self._group_path)
        return self._group

    def get(self, name: str) -> Optional[Project]:
        """Get a specific project by name."""

        if name in self._cache:
            logger.debug("Cache hit for project: %s", name)
            return self._cache[name]

        try:
            logger.debug("Fetching project details for: %s", name)
            projects = self.group.projects.list(search=name, include_subgroups=True)

            for project in projects:
                if project.name == name:
                    full_project = self._gitlab.projects.get(project.id)
                    if hasattr(full_project, "archived") and full_project.archived:
                        logger.debug(
                            "Found project %s but it is archived, skipping",
                            name,
                        )
                        continue
                    wrapper = GitLabProject(full_project)
                    self._cache[name] = wrapper
                    logger.debug("Cached project: %s", name)
                    return wrapper

            logger.debug("Project %s not found or is archived", name)
            return None
        except GitlabError as e:
            logger.error("Error fetching project %s: %s", name, str(e))
            return None

    def get_projects_for_namespace(self, namespace_path: str) -> Optional["Projects"]:
        """Get projects collection for a group by namespace path."""
        try:
            logger.debug("Getting projects for namespace path: %s", namespace_path)
            # Verify the group exists
            group = self._gitlab.groups.get(namespace_path)
            logger.debug("Successfully retrieved group: %s (ID: %s)", namespace_path, group.id)
            return GitLabProjects(namespace_path, self._gitlab)
        except GitlabError as e:
            logger.debug("Failed to get group %s: %s", namespace_path, str(e))
            return None

    def hierarchy_exists(self, target_path: str) -> bool:
        """Check if a hierarchy exists at the target path."""
        projects = self.get_projects_for_namespace(target_path)
        if projects:
            logger.info("Target hierarchy '%s' already exists", target_path)
            return True
        return False

    def create_subgroup(self, subgroup_path: str) -> bool:
        """Create a subgroup hierarchy."""
        try:
            parent_group_gitlab = self._gitlab.groups.get(self._group_path)
            if not parent_group_gitlab:
                logger.error("Parent group %s not found", self._group_path)
                return False

            parts = subgroup_path.split("/")
            current_path = self._group_path
            current_parent_id = parent_group_gitlab.id

            for part in parts:
                current_path = f"{current_path}/{part}"
                try:
                    existing_group = self._gitlab.groups.get(current_path)
                    current_parent_id = existing_group.id
                    logger.debug("Subgroup %s already exists", current_path)
                except GitlabError:
                    logger.info("Creating subgroup: %s", current_path)
                    new_group = self._gitlab.groups.create(
                        {"name": part, "path": part, "parent_id": current_parent_id}
                    )
                    current_parent_id = new_group.id
                    logger.info("Successfully created subgroup: %s", current_path)

            return True
        except GitlabError as e:
            logger.error("Failed to create subgroup %s: %s", subgroup_path, str(e))
            return False

    def get_group_id(self, namespace_path: str) -> Optional[int]:
        """Get group ID for a namespace path."""
        try:
            group = self._gitlab.groups.get(namespace_path)
            return group.id
        except GitlabError as e:
            logger.debug("Failed to get group ID for %s: %s", namespace_path, str(e))
            return None
