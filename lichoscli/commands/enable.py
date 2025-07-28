import logging

from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils, CIConfigUtils


logger = logging.getLogger(__name__)


class EnableCommand(Command):
    """enable package build"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.type = args.type
        self.ci_branch = args.ci_branch

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("type", nargs="?", help="build type name")
        sp.add_argument(
            "ci_branch", nargs="?", default=None,
            help="branch name for some commands, defaults to current branch",
        )
        
    def execute(self):
        ci_config = CIConfigUtils.get_ci_path(
            self.pkg_group_handler.group_rpath, self.type,
        branch=self.ci_branch) if self.type else None
        logger.debug(f"CI config path: {ci_config}")


        pkg = self.pkg_group_handler.update_package(
            self.package_name, access_level="enabled", ci_config_path=ci_config,
        )

        if pkg is None:
            logger.error("Package %s could not be enabled", self.package_name)
            return 1
        return 0
