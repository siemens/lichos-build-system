"""GitLab group service implementation."""

import logging
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.services import GroupService
from lichoscli.core.models import Group
from lichoscli.providers.gitlab.models import GitLabGroupWrapper

logger = logging.getLogger(__name__)


class GitLabGroupService(GroupService):
    """GitLab implementation of group management operations."""

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab

    def get_group(self, namespace_path: str) -> Optional[Group]:
        try:
            logger.debug("Getting group for namespace path: %s", namespace_path)
            group = self.gitlab.groups.get(namespace_path)
            logger.debug(
                "Successfully retrieved group: %s (ID: %s)", namespace_path, group.id
            )
            return GitLabGroupWrapper(group)
        except GitlabError as e:
            logger.debug("Failed to get group %s: %s", namespace_path, str(e))
            return None

    def hierarchy_exists(self, target_path: str) -> bool:
        """Check if a hierarchy exists at the target path."""
        group = self.get_group(target_path)
        if group:
            logger.info("Target hierarchy '%s' already exists", target_path)
            return True
        return False

    def create_subgroup(self, subgroup_path: str) -> bool:
        try:
            parent_group = self.get_group(self.group_rpath)
            if not parent_group:
                logger.error("Parent group '%s' not found", self.group_rpath)
                return False

            subgroup_parts = subgroup_path.split("/")
            current_parent_id = parent_group.gitlab_group.id
            current_path = self.group_rpath

            for part in subgroup_parts:
                current_path = f"{current_path}/{part}"

                existing_group = self.get_group(current_path)
                if existing_group:
                    logger.debug("Group '%s' already exists", current_path)
                    current_parent_id = existing_group.gitlab_group.id
                    continue

                group_data = {
                    "name": part,
                    "path": part,
                    "description": f"Auto-generated subgroup: {part}",
                    "visibility": "internal",
                    "parent_id": current_parent_id,
                }

                logger.debug("Creating subgroup: %s", current_path)
                new_group = self.gitlab.groups.create(group_data)
                current_parent_id = new_group.id
                logger.debug(
                    "Created subgroup '%s' with ID %d", current_path, new_group.id
                )

            return True

        except GitlabError as e:
            logger.error(
                "GitLab API error creating subgroup '%s': %s", subgroup_path, str(e)
            )
            return False
