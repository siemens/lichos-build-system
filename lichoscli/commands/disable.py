import logging
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class DisableCommand(Command):
    """Disable package builds"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")

    def execute(self):
        if self.package_name is None:
            logger.error("Package name must be specified")
            return 1
        pkg = self.pkg_group_handler.update_package(
            self.package_name, access_level="disabled"
        )
        if pkg is None:
            logger.error("Package %s could not be disabled", self.package_name)
            return 1
        return 0
