import logging
from typing import List

from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import CI_PKG, REQUIRED_PACKAGES

logger = logging.getLogger(__name__)


class HierarchyCommand(Command):
    """Create a package hierarchy at a specific path based on another available one"""

    # Constants for required packages and group variables
    GROUP_VARIABLES = [
        "PROD_NEXUS_AUTH (masked, protected)",
        "RMS_PLATFORM_TOKEN (masked, protected)",
    ]

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument(
            "target_path",
            help="target path for the new hierarchy (e.g., 'mygroup/myhierarchy')",
        )

    def execute(self) -> int:
        """Execute the hierarchy command."""
        logger.info(
            "Creating hierarchy at '%s' based on current hierarchy '%s'",
            self.args.target_path,
            self.pkg_group_handler.group_rpath,
        )

        if self.args.dry:
            logger.info(
                "DRY RUN: Would create hierarchy with the following configuration:"
            )
            return self._dry_run_preview()

        if self.pkg_group_handler.hierarchy_exists(self.args.target_path):
            logger.info(
                "Hierarchy already exists at '%s', using existing one",
                self.args.target_path,
            )
            target_pkg_handler = PkgGroupHandler(
                self.args.target_path, self.pkg_group_handler.gitlab
            )
        else:
            target_pkg_handler = self._create_target_hierarchy()

        if not self._fork_required_packages(target_pkg_handler):
            logger.error("Failed to fork required packages")
            return 1

        logger.info("Successfully created hierarchy at '%s'", self.args.target_path)
        self._print_manual_setup_instructions()
        target_group = target_pkg_handler.get_group(self.args.target_path)
        logger.info("Hierarchy created successfully at: %s", target_group.web_url)
        return 0

    def _create_target_hierarchy(self) -> PkgGroupHandler:
        """Create the target hierarchy group structure."""
        path_parts: List[str] = self.args.target_path.split("/")
        current_path = ""

        for i, part in enumerate(path_parts):
            if i == 0:
                current_path = part
            else:
                current_path = "{}/{}".format(current_path, part)
            existing_group = self.pkg_group_handler.get_group(current_path)
            if existing_group:
                logger.debug("Group '%s' already exists", current_path)
                continue
            parent_path = "/".join(path_parts[:i]) if i > 0 else None
            parent_group = (
                self.pkg_group_handler.get_group(parent_path) if parent_path else None
            )
            parent_id = parent_group.id if parent_group else None
            group_data = {
                "name": part,
                "path": part,
                "description": "Auto-forked hierarchy group: {}".format(part),
                "visibility": "internal",
            }
            if parent_id:
                group_data["parent_id"] = parent_id
            logger.info("Creating group: %s", current_path)
            self.pkg_group_handler.gitlab.groups.create(group_data)
        return PkgGroupHandler(self.args.target_path, self.pkg_group_handler.gitlab)

    def _fork_required_packages(self, target_pkg_handler: PkgGroupHandler) -> bool:
        """Fork required packages to target hierarchy."""
        for package_name in REQUIRED_PACKAGES:
            source_package = self.pkg_group_handler.get_package(package_name)
            if not source_package:
                logger.warning(
                    "Package '%s' not found in source hierarchy, skipping", package_name
                )
                continue

            logger.info("Forking package '%s' to target hierarchy", package_name)
            forked_package = target_pkg_handler.fork_package(source_package)

            if not forked_package:
                logger.error("Failed to fork package '%s'", package_name)
                return False

            logger.debug(
                "Successfully forked package '%s' to '%s'",
                package_name,
                forked_package.path_with_namespace,
            )
        return True

    def _dry_run_preview(self) -> int:
        """Preview what would be done in a dry run."""
        print("DRY RUN PREVIEW:")
        print("Target hierarchy: {}".format(self.args.target_path))
        print("Source hierarchy: {}".format(self.pkg_group_handler.group_rpath))
        print()

        if self.pkg_group_handler.hierarchy_exists(self.args.target_path):
            print(
                "NOTE: Hierarchy already exists at '{}', would use existing one".format(
                    self.args.target_path
                )
            )
            print("Actions that would be performed:")
        else:
            print("Actions that would be performed:")
            print(
                "1. Create hierarchy group structure at: {}".format(
                    self.args.target_path
                )
            )

        self._preview_package_forks()
        print("3. Note: You will need to manually set the following group variables:")
        for variable in self.GROUP_VARIABLES:
            print("   - {}".format(variable))
        print("   - CI_00CI_PROJECT_PATH: {}/{}".format(self.args.target_path, CI_PKG))

        return 0

    def _preview_package_forks(self) -> None:
        """Preview package fork operations for dry run."""
        for package_name in REQUIRED_PACKAGES:
            source_package = self.pkg_group_handler.get_package(package_name)
            if source_package:
                print("2. Fork {} from: {}".format(package_name, source_package.path_with_namespace))
                print("   To: {}/{}".format(self.args.target_path, package_name))
                default_branch = getattr(source_package, "default_branch", None) or "main (fallback)"
                print("   Default branch: {}".format(default_branch))
            else:
                print("2. WARNING: {} not found in source hierarchy".format(package_name))

    def _print_manual_setup_instructions(self) -> None:
        """Print instructions for manual group variable setup."""
        print("IMPORTANT: You must manually set the following group variables:")
        for variable in self.GROUP_VARIABLES:
            print("  - {}".format(variable))
        print("  - CI_00CI_PROJECT_PATH: {}/{}".format(self.args.target_path, CI_PKG))
