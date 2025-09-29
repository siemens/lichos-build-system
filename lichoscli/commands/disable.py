import logging

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class DisableCommand(Command):
    """Disable package builds"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")

    def execute(self):
        if self.package_name is None:
            logger.error("Package name must be specified")
            return 1
        pkg = self.package_service.update_package(self.package_name, access_level="disabled")
        if pkg is None:
            logger.error("Package %s could not be disabled", self.package_name)
            return 1
        return 0
