# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from datetime import datetime

from git import GitCommandError

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models.git import GitRepo
from lichoscli.core.exceptions import BranchError, ValidationError
from lichoscli.core.services import SubmoduleService

logger = logging.getLogger(__name__)


class SnapshotCommand(Command):
    """Snapshot the submodule project by updating submodules and tagging"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.submodule_service = di_container.obtain_ref(SubmoduleService)

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

        committed = False
        if self.args.dry:
            logger.info("DRY RUN: Would synchronize submodules with workspace %s", branch)
        else:
            try:
                committed = bool(self.submodule_service.update(git_repo.path, branch))
            except (BranchError, ValidationError) as e:
                logger.error("%s", e)
                return 1

        if not self._tag_push(git_repo, committed, tag):
            return 1

        logger.info("Snapshot completed successfully: %s", tag)
        return 0

    def _tag_push(self, git_repo: GitRepo, committed: bool, tag: str) -> bool:
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
