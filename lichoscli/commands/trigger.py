import logging

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class TriggerCommand(Command):
    """Trigger package build"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package) if args.package else None
        self.all_packages = args.all
        self.branch = args.branch
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("--all", action="store_true", help="trigger all packages")

    def execute(self):
        if self.package_name:
            return self._trigger_single_package()

        if self.all_packages:
            return self._trigger_all_packages()

        logger.error("Please specify a package or use --all to trigger all packages.")
        return 1

    def _trigger_single_package(self):
        """Trigger build for a single specified package."""
        package = self.package_service.get_package(self.package_name)
        return package.pipelines.trigger_build(self.branch)

    def _trigger_all_packages(self):
        """Trigger builds for all eligible packages."""
        eligible_packages = self._get_eligible_packages()

        if not eligible_packages:
            logger.warning("No eligible packages found for branch %s", self.branch or "default")
            return 0

        logger.info(
            "Triggering builds for %d packages with branch %s",
            len(eligible_packages),
            self.branch or "default",
        )

        return self._execute_builds(eligible_packages)

    def _get_eligible_packages(self):
        """Get list of packages eligible for build triggering."""
        eligible_packages = []

        for package in self.package_service.get_all_packages():
            if not self._is_package_eligible(package):
                continue
            eligible_packages.append(package)

        return eligible_packages

    def _is_package_eligible(self, package):
        """Check if a package is eligible for build triggering."""
        if not package.ci_config_path:
            return False

        if self.branch and not package.has_branch(self.branch):
            logger.debug(
                "Package %s does not have branch %s, skipping",
                package.name,
                self.branch,
            )
            return False

        return True

    def _execute_builds(self, packages):
        """Execute builds for the given list of packages."""
        result = 0

        for package in packages:
            result += package.pipelines.trigger_build(self.branch)

        if result != 0:
            logger.error("one or more packages failed to trigger build, please check the logs.")

        return result
