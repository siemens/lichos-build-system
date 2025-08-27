import logging

from gitlab import GitlabError
from lichoscli.commands.base import Command
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class TriggerCommand(Command):
    """Trigger package build"""

    def __init__(self, pkg_group_handler, args):
        super().__init__(pkg_group_handler, args)
        self.package_name = BuildUtils.get_package_name(args.package) if args.package else None
        self.all_packages = args.all
        self.branch = args.branch

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
        package = self.pkg_group_handler.get_package(self.package_name)
        return self.pkg_group_handler.trigger_package_build(package, self.branch)

    def _trigger_all_packages(self):
        """Trigger builds for all eligible packages."""
        eligible_packages = self._get_eligible_packages()
        
        if not eligible_packages:
            logger.warning("No eligible packages found for branch %s", self.branch or "default")
            return 0
        
        logger.info("Triggering builds for %d packages with branch %s", 
                   len(eligible_packages), self.branch or "default")
        
        return self._execute_builds(eligible_packages)

    def _get_eligible_packages(self):
        """Get list of packages eligible for build triggering."""
        eligible_packages = []
        
        for package in self.pkg_group_handler.get_all_packages():
            if not self._is_package_eligible(package):
                continue
            eligible_packages.append(package)
        
        return eligible_packages

    def _is_package_eligible(self, package):
        """Check if a package is eligible for build triggering."""
        if not package.ci_config_path:
            return False
        
        if self.branch and not self.has_branch(package, self.branch):
            logger.debug("Package %s does not have branch %s, skipping", 
                        package.name, self.branch)
            return False
        
        return True

    def _execute_builds(self, packages):
        """Execute builds for the given list of packages."""
        result = 0
        
        for package in packages:
            result += self.pkg_group_handler.trigger_package_build(package, self.branch)
        
        if result != 0:
            logger.error("one or more packages failed to trigger build, please check the logs.")
        
        return result

    def has_branch(self, package, branch_name):
        """Check if a package has the specified branch"""
        try:
            if not hasattr(package, 'branches'):
                logger.debug("Package %s doesn't have branches attribute, assuming branch exists", package.name)
                return False
                
            branches = package.branches.list(all=True)
            branch_names = [branch.name for branch in branches]
            return branch_name in branch_names
        except GitlabError as e:
            logger.warning("Failed to get branches for package %s: %s", package.name, str(e))
            return False