import logging
from lichoscli.commands.base import Command

logger = logging.getLogger(__name__)


class TriggerCommand(Command):
    """trigger package build"""

    def __init__(self, pkg_group_handler, args):
        super().__init__(pkg_group_handler, args)
        self.package_name = args.package
        self.all_packages = args.all
        self.branch = args.branch

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("--all", action="store_true", help="trigger all packages")

    def execute(self):
        if self.package_name:
            package = self.pkg_group_handler.get_package(self.package_name)
            return self.pkg_group_handler.trigger_package_build(package, self.branch)

        if self.all_packages:
            result = 0
            for package in self.pkg_group_handler.get_all_packages():
                if package.ci_config_path:
                    result += self.pkg_group_handler.trigger_package_build(package, self.branch)
            if result != 0:
                logger.error(
                    "one or more packages failed to trigger build, please check the logs."
                )
            return result
        else:
            logger.error(
                "Please specify a package or use --all to trigger all packages."
            )
            return 1
