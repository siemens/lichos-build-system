import logging

from gitlab.v4.objects import Project

from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import CI_PKG, CIConfigUtils, HierarchyUtils

logger = logging.getLogger(__name__)


class ForkCommand(Command):
    """Fork a package from source hierarchy to destination namespace

    If no namespace is provided, auto-detects configuration from 00ci:
    - If current 00ci is forked, uses its parent as source and current hierarchy as destination
    - Otherwise, requires explicit namespace parameter
    """

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.source_hierarchy = None
        self.destination_namespace = None
        self._detect_fork_configuration()

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="package name to fork from base hierarchy")
        sp.add_argument("namespace", nargs='?', help="destination namespace to fork to (auto-detected if not provided)")

    def validate_args(self) -> None:
        """Validate command-specific arguments."""
        if not self.args.package or not self.args.package.strip():
            raise ValueError("Package name cannot be empty")
        
        if self.args.namespace and not self.args.namespace.strip():
            raise ValueError("Namespace cannot be empty if provided")

    def execute(self) -> int:
        """Execute the fork command."""
        logger.info("Forking package '%s' from '%s' to destination namespace '%s'",
                    self.args.package,
                    self.source_hierarchy.group_rpath,
                    self.destination_namespace)

        if self.args.dry:
            logger.info("DRY RUN: Would fork package with the following configuration:")
            return self._dry_run_preview()

        # Check if destination hierarchy exists
        if not self.pkg_group_handler.hierarchy_exists(self.destination_namespace):
            logger.error("Target hierarchy '%s' does not exist", self.destination_namespace)
            return 1

        destination_pkg_handler = PkgGroupHandler(self.destination_namespace, self.pkg_group_handler.gitlab)

        # Check if 00ci exists in destination namespace
        destination_ci = destination_pkg_handler.get_package(CI_PKG)
        if not destination_ci:
            logger.error("00ci package not found in destination hierarchy '%s'", self.destination_namespace)
            return 1

        # Get the base package from source hierarchy
        base_package = self.source_hierarchy.get_package(self.args.package)
        if not base_package:
            logger.error("Package '%s' not found in source hierarchy '%s'",
                         self.args.package, self.source_hierarchy.group_rpath)
            return 1

        subpath = HierarchyUtils.extract_package_subpath(
            base_package.path_with_namespace,
            self.source_hierarchy.group_rpath
        )

        # Fork the package to destination namespace with preserved subpath
        forked_package = destination_pkg_handler.fork_package(base_package, subpath)
        if not forked_package:
            logger.error("Failed to fork package '%s' to destination namespace", self.args.package)
            return 1

        # Configure CI settings to use destination namespace's 00ci
        ci_config_path = self._configure_forked_package_ci(forked_package, destination_pkg_handler)

        logger.info("Successfully forked package '%s' to '%s'",
                    self.args.package, self.destination_namespace)
        logger.info("Forked package CI/CD configured to use: %s", ci_config_path)
        return 0

    def _configure_forked_package_ci(self, forked_package: Project, destination_pkg_handler: PkgGroupHandler) -> str:
        """Configure CI/CD settings for the forked package to use destination namespace's 00ci.

        Returns:
            The CI config path that was configured, or None if configuration failed.
        """
        package_type = self._determine_package_type(forked_package)
        logger.debug("Detected package type: %s", package_type)

        ci_config_path = CIConfigUtils.get_ci_path(
            destination_pkg_handler.group_rpath,
            ci_typ=package_type
        )

        logger.info("Configuring CI/CD to use: %s", ci_config_path)

        forked_package.ci_config_path = ci_config_path
        forked_package.save()

        logger.info("Successfully configured CI/CD settings")
        return ci_config_path

    def _determine_package_type(self, package: Project) -> str:
        """Determine if package is image or gbp type by examining its current CI config."""
        current_ci_path = package.ci_config_path
        if current_ci_path and current_ci_path != '.gitlab-ci.yml':
            parsed = CIConfigUtils.parse_ci_config_path(current_ci_path)
            if parsed and parsed.name:
                logger.debug("Detected package type from CI config: %s", parsed.name)
                return parsed.name

        logger.debug("Could not determine package type, defaulting to gbp")
        return current_ci_path

    def _dry_run_preview(self) -> int:
        """Preview what would be done in a dry run."""
        print("DRY RUN PREVIEW:")
        print("Package to fork: {}".format(self.args.package))
        print("Source hierarchy: {}".format(self.source_hierarchy.group_rpath))
        print("Destination namespace: {}".format(self.destination_namespace))

        # Check if target hierarchy exists
        if not self.pkg_group_handler.hierarchy_exists(self.destination_namespace):
            print("ERROR: Target hierarchy '{}' does not exist.".format(self.destination_namespace))
            print("Please create the hierarchy first using: lichoscli hierarchy {}".format(self.destination_namespace))
            return 1

        # Check if base package exists
        base_package = self.source_hierarchy.get_package(self.args.package)
        if not base_package:
            print("ERROR: Package '{}' not found in source hierarchy".format(self.args.package))
            return 1

        print("Source package: {}".format(base_package.path_with_namespace))

        # Extract the relative subpath to preserve directory structure
        subpath = HierarchyUtils.extract_package_subpath(
            base_package.path_with_namespace,
            self.source_hierarchy.group_rpath
        )

        destination_pkg_handler = PkgGroupHandler(self.destination_namespace, self.pkg_group_handler.gitlab)

        # Check if 00ci exists in destination
        destination_ci = destination_pkg_handler.get_package(CI_PKG)
        if destination_ci:
            print("00ci exists in destination: {}".format(destination_ci.path_with_namespace))
        else:
            print("ERROR: 00ci not found in target hierarchy '{}'.".format(self.destination_namespace))
            print("Please create the hierarchy first using: lichoscli hierarchy {}".format(self.destination_namespace))
            return 1

        if subpath:
            target_path = "{}/{}/{}".format(self.destination_namespace, subpath, self.args.package)
        else:
            target_path = "{}/{}".format(self.destination_namespace, self.args.package)
        print("Target location: {}".format(target_path))

        package_type = self._determine_package_type(base_package)
        ci_config_path = CIConfigUtils.get_ci_path(
            self.destination_namespace,
            ci_typ=package_type
        )
        print("CI/CD will be configured to: {}".format(ci_config_path))

        return 0

    def _detect_fork_configuration(self):
        """Detect source hierarchy and destination namespace based on 00ci fork status."""
        current_ci = self.pkg_group_handler.get_package(CI_PKG)

        if self.args.namespace:
            self.source_hierarchy = self.pkg_group_handler
            self.destination_namespace = self.args.namespace
            logger.debug("Using explicit namespace: %s", self.args.namespace)
            return

        if not current_ci:
            logger.error("No 00ci package found in current hierarchy")
            raise ValueError("Cannot auto-detect configuration without 00ci package")
        if hasattr(current_ci, 'forked_from_project') and current_ci.forked_from_project:
            parent_namespace = current_ci.forked_from_project['namespace']['full_path']
            logger.info("Detected forked 00ci from parent hierarchy: %s", parent_namespace)
            self.source_hierarchy = PkgGroupHandler(parent_namespace, self.pkg_group_handler.gitlab)
            self.destination_namespace = self.pkg_group_handler.group_rpath
            logger.info("Auto-detected fork configuration:")
            logger.info("  Source hierarchy: %s", parent_namespace)
            logger.info("  Destination: %s", self.destination_namespace)
        else:
            logger.error("Current 00ci is not forked from a parent hierarchy")
            logger.error("Please provide an explicit destination namespace or ensure 00ci is forked")
            raise ValueError("Cannot auto-detect configuration: 00ci is not forked")
