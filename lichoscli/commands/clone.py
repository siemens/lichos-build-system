import logging
import os

import git
from git.repo import Repo
from git.exc import GitCommandError
import yaml

from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils


logger = logging.getLogger(__name__)


class CloneCommand(Command):
    """clone a package"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.branch = args.branch if hasattr(args, "branch") else None

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="package name")

    def execute(self):
        package = self.pkg_group_handler.get_package(self.package_name)
        if not package:
            logger.error("Package '%s' not found", self.package_name)
            return 1
            
        repo_url = package.ssh_url_to_repo
        if self.branch:
            try:
                repo = Repo.clone_from(
                    repo_url, self.package_name, branch=self.branch
                )
            except GitCommandError as e:
                logger.warning("Failed to checkout %s: %s", self.branch, e)
                logger.warning(
                    "Checkout default branch and create local branch %s", self.branch
                )
                repo = Repo.clone_from(repo_url, self.package_name)
                repo.git.checkout("-b", self.branch)
        else:
            repo = Repo.clone_from(repo_url, self.package_name)

        if hasattr(package, 'forked_from_project') and package.forked_from_project:
            logger.debug(package.forked_from_project)
            purl = package.forked_from_project.get('ssh_url_to_repo', None)
            if purl:
                logger.debug("Adding parent %s", purl)
                parent = repo.create_remote("parent", purl)
                parent.fetch()

        fn = os.path.join(self.package_name, "debian/upstream/metadata")
        if os.path.exists(fn):
            logger.debug("Found upstream metadata %s", fn)
            with open(fn, "r", encoding="utf-8") as fh:
                y = yaml.safe_load(fh)
                if u := y.get("Repository", None):
                    logger.debug("Adding upstream %s", u)
                    upstream = repo.create_remote("upstream", u)
                    upstream.fetch()

        return 0
