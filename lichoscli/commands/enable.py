import logging

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils
from lichoscli.utils.ci import CIConfigUtils

logger = logging.getLogger(__name__)


class EnableCommand(Command):
    """Enable package builds"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.type = args.type
        self.ci_branch = args.ci_branch
        self.package_service = di_container.obtain_ref(PackageService)
        self.group_rpath = self.package_service.get_projects().path

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument(
            "--type",
            dest="type",
            required=False,
            help="build type name",
        )
        sp.add_argument(
            "--ci-branch",
            dest="ci_branch",
            required=False,
            default=None,
            help="branch name for some commands, defaults to current branch",
        )

    def execute(self):
        ci_config = (
            CIConfigUtils.get_ci_path(self.group_rpath, self.type, branch=self.ci_branch) if self.type else None
        )
        logger.debug("CI config path: %s", ci_config)

        pkg = self.package_service.update_package(
            self.package_name,
            access_level="enabled",
            ci_config_path=ci_config,
        )

        if pkg is None:
            logger.error("Package %s could not be enabled", self.package_name)
            return 1
        return 0
