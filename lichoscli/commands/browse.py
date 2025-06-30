import logging
import subprocess

import git
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class BrowseCommand(Command):
    """open browser"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.branch = args.branch

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")

    def execute(self):
        pkg = self.pkg_group_handler.get_package(self.package_name)
        if pkg is None:
            logger.error("Package not found: %s", self.package_name)
            return 1

        url = pkg.web_url
        branch = self.branch
        if self.branch is None:
            try:
                repo = git.Repo(".")
                branch = str(repo.head.reference)
            except git.exc.InvalidGitRepositoryError:
                logger.error("Invalid repository: %s", self.package_name)
                return 1

        url = f"{url}/tree/{branch}"
        logger.info("Opening URL: %s", url)

        r = subprocess.run(("xdg-open", url), check=True)
        return r.returncode
