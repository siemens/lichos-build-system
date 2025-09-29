import logging
import os

import yaml
from git.exc import GitCommandError
from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class CloneCommand(Command):
    """Clone a package repository"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="package name")

    def execute(self):
        package = self.package_service.get_package(self.package_name)
        if not package:
            logger.error("Package '%s' not found", self.package_name)
            return 1

        repo_url = package.ssh_url_to_repo
        if self.args.branch:
            try:
                repo = Repo.clone_from(repo_url, self.package_name, branch=package.default_branch)
            except GitCommandError as e:
                logger.warning("Failed to checkout %s: %s", self.args.branch, e)
                logger.warning(
                    "Checkout default branch and create local branch %s",
                    self.args.branch,
                )
                repo = Repo.clone_from(repo_url, self.package_name, branch=package.default_branch)
                repo.git.checkout("-b", self.args.branch)
        else:
            repo = Repo.clone_from(repo_url, self.package_name, branch=package.default_branch)

        if package.is_fork:
            purl = package.parent_ssh_url_to_repo
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
