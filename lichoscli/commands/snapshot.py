# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from datetime import datetime

from git import GitCommandError

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models.git import GitRepo
from lichoscli.core.services import PackageService

logger = logging.getLogger(__name__)


class SnapshotCommand(Command):
    """Snapshot the submodule project by updating submodules and tagging"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument(
            "-p",
            "--submodule-project",
            required=True,
            help="Path or URL to the git project containing package submodules",
        )
        sp.add_argument(
            "--push",
            action="store_true",
            default=False,
            help="Push changes and tags to remote repository",
        )

    def execute(self) -> int:
        """Execute the snapshot process"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag = f"v{timestamp}"
        
        project_location = self.args.submodule_project
        branch = self.args.branch
        
        logger.info("Snapshotting submodule project at %s on branch %s with tag %s", 
                    project_location, branch, tag)

        git_repo = GitRepo.get_or_clone(project_location, branch)
        if not git_repo:
            return 1
            
        updated_names = self._update_submodules(git_repo, branch)
        
        if not self._commit_tag_push(git_repo, updated_names, tag):
            return 1
            
        logger.info("Snapshot completed successfully: %s", tag)
        return 0

    def _update_submodules(self, git_repo: GitRepo, branch: str) -> list[str]:
        updated_names = []
        
        if not git_repo.submodules:
            logger.warning("No submodules found in repository")
            return []

        for submodule in git_repo.submodules:
            package = self.package_service.get_package(submodule.name)
            if not package:
                logger.warning("Package '%s' not found in GitLab", submodule.name)
                continue

            branch_obj = self.package_service.get_package_branch(package, branch)
            if not branch_obj:
                logger.warning("Branch '%s' not found for package '%s'", branch, package.name)
                continue

            latest_sha = branch_obj.commit["id"]
            current_sha = submodule.hexsha

            if current_sha != latest_sha:
                if git_repo.update_submodule_commit(submodule.path, latest_sha):
                    logger.info("Updated submodule '%s': %s -> %s", submodule.name, current_sha[:8], latest_sha[:8])
                    updated_names.append(submodule.name)
        
        return updated_names

    def _commit_tag_push(self, git_repo: GitRepo, updated_names: list[str], tag: str) -> bool:
        committed = False
        if updated_names:
            if self.args.dry:
                logger.info("DRY RUN: Would commit submodule updates: %s", ", ".join(updated_names))
            else:
                commit_message = f"Snapshot update: {tag}"
                committed = git_repo.commit(commit_message)

        if self.args.dry:
             logger.info("DRY RUN: Would create tag %s", tag)
             if self.args.push:
                 logger.info("DRY RUN: Would push changes and tags")
             return True

        try:
            git_repo.repo.create_tag(tag, message=f"Snapshot {tag}")
            logger.info("Created tag: %s", tag)
        except GitCommandError as e:
            logger.error("Failed to create tag %s: %s", tag, e)
            return False

        if self.args.push:
             if committed:
                 if not git_repo.push_branch():
                     logger.error("Failed to push branch")
                     return False
             if not git_repo.push_tags():
                 logger.error("Failed to push tags")
                 return False
                 
        return True
