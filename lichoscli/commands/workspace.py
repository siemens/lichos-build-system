import logging
import os
import subprocess
from lichoscli.utils import BuildUtils, GitUtils
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler


logger = logging.getLogger(__name__)


class WorkspaceCommand(Command):
    """Set workspace branch"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("action", help="action to perform", choices=["enter"])
        sp.add_argument("workspace_branch", nargs="?", help="branch name")

    def action_enter(self):
        """Enter the workspace with the specified branch."""

        # prefer branch specifed as argument for command
        branch = self.args.workspace_branch

        # fall back to global branch option (also set from env var)
        if not branch:
            branch = self.args.branch

        # otherwise use branch from current repo
        if not branch:
            repo = GitUtils.get_git_repo()
            if repo:
                branch = repo.active_branch.name

        if not branch:
            logger.error('Please specify branch')
            return 1

        os.environ["LICHOS_BRANCH"] = branch

        logger.info("entering workspace %s", branch)

        r = subprocess.run([os.environ.get("SHELL", "/bin/sh")])
        return r.returncode

    def execute(self):
        if self.args.action == "enter":
            return self.action_enter()

        return 1
