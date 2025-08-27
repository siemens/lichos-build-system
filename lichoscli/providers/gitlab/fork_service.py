"""GitLab fork service implementation."""

import logging
import time
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.services import ForkService
from lichoscli.core.models import Project
from lichoscli.providers.gitlab.models import GitLabProjectWrapper
from .package_service import GitLabPackageService
from .group_service import GitLabGroupService

logger = logging.getLogger(__name__)


class GitLabForkService(ForkService):
    """GitLab implementation of forking operations."""

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab

    def fork_package(
        self, parent_package: Project, subgroup: Optional[str] = None
    ) -> Optional[Project]:
        """Fork a package to the current hierarchy with optional subgroup"""
        if not isinstance(parent_package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = parent_package.gitlab_project

        try:
            target_namespace_path = f"{self.group_rpath}/{subgroup or ''}".rstrip("/")

            group_service = GitLabGroupService(self.group_rpath, self.gitlab)
            target_group = group_service.get_group(target_namespace_path)

            if not target_group:
                if subgroup:
                    # Try to create the subgroup if it doesn't exist
                    logger.info(
                        "Target subgroup '%s' not found, attempting to create it",
                        subgroup,
                    )
                    if group_service.create_subgroup(subgroup):
                        target_group = group_service.get_group(target_namespace_path)
                    else:
                        logger.error("Failed to create subgroup '%s'", subgroup)
                        return None

                if not target_group:
                    logger.error("Target group '%s' not found", target_namespace_path)
                    return None

            target_namespace_id = target_group.gitlab_group.id

            # Check if package already exists
            package_service = GitLabPackageService(self.group_rpath, self.gitlab)
            existing_package = package_service.get_package(parent_package.name)
            if existing_package:
                logger.error(
                    "Package '%s' already exists in current hierarchy",
                    existing_package.name,
                )
                return None

            logger.info(
                "Forking package from %s to %s",
                parent_package.path_with_namespace,
                target_namespace_path,
            )

            fork_data = {
                "namespace_id": target_namespace_id,
                "name": parent_package.name,
                "path": parent_package.name,
            }

            gitlab_pkg.forks.create(fork_data)
            package_service.invalidate_cache()

            # Wait for fork to be ready with retry pattern
            forked_package = None
            for _ in range(3):  # Max 3 attempts
                forked_package = package_service.get_package(parent_package.name)
                if forked_package:
                    break
                time.sleep(1)

            if not forked_package:
                logger.error("Fork created but package not found after retries")
                return None

            logger.info(
                "Successfully forked package: %s", forked_package.path_with_namespace
            )
            return forked_package

        except GitlabError as e:
            logger.error("GitLab API error forking package: %s", str(e))
            return None
