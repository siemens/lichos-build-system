# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.exceptions import ProviderAPIError
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
from lichoscli.utils import CI_PKG, CORE_PACKAGES

logger = logging.getLogger(__name__)


class HierarchyCommand(Command):
    """Create a package hierarchy at a specific path based on another available one"""

    GROUP_VARIABLES = [
        "PROD_NEXUS_AUTH (masked, protected)",
        "RMS_PLATFORM_TOKEN (masked, protected)",
    ]

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.projects = self.package_service.get_projects()

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
            self.di_container.group_rpath,
        )

        if self.args.dry:
            logger.info("DRY RUN: Would create hierarchy with the following configuration:")
            return self._dry_run_preview()

        if self.projects.hierarchy_exists(self.args.target_path):
            logger.info(
                "Hierarchy already exists at '%s', using existing one",
                self.args.target_path,
            )
        else:
            self._create_target_hierarchy()

        if not self._fork_required_packages():
            logger.error("Failed to fork required packages")
            return 1

        logger.info("Successfully created hierarchy at '%s'", self.args.target_path)
        self.output.warning("IMPORTANT: You must manually set the following group variables:")
        for variable in self.GROUP_VARIABLES:
            self.output.print(f"  - {variable}")
        self.output.print(f"  - CI_00CI_PROJECT_PATH: {self.args.target_path}/{CI_PKG}")
        target_projects = self.projects.get_projects_for_namespace(self.args.target_path)
        if target_projects:
            logger.info("Hierarchy created successfully at: %s", self.args.target_path)
        return 0

    def _create_target_hierarchy(self) -> bool:
        """Create the target hierarchy group structure."""
        path_parts: list[str] = self.args.target_path.split("/")
        current_path = ""

        for i, part in enumerate(path_parts):
            if i == 0:
                current_path = part
            else:
                current_path = f"{current_path}/{part}"

            existing_projects = self.projects.get_projects_for_namespace(current_path)
            if existing_projects:
                logger.debug("Group '%s' already exists", current_path)
                continue
            parent_path = "/".join(path_parts[:i]) if i > 0 else None
            try:
                parent_group_gitlab = self.di_container.gitlab.groups.get(parent_path) if parent_path else None
                parent_id = parent_group_gitlab.id if parent_group_gitlab else None
            except ProviderAPIError:
                parent_id = None
            group_data = {
                "name": part,
                "path": part,
                "description": f"Auto-forked hierarchy group: {part}",
                "visibility": "internal",
            }
            if parent_id:
                group_data["parent_id"] = parent_id
            logger.info("Creating group: %s", current_path)
            self.di_container.gitlab.groups.create(group_data)
        return True

    def _fork_required_packages(self) -> bool:
        """Fork required packages to target hierarchy."""
        for package_name in CORE_PACKAGES:
            source_package = self.package_service.get_package(package_name)
            if not source_package:
                logger.warning("Package '%s' not found in source hierarchy, skipping", package_name)
                continue

            logger.info("Forking package '%s' to target hierarchy", package_name)
            forked_package = source_package.fork_to(self.args.target_path)

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
        self.output.accent("DRY RUN PREVIEW:")
        self.output.print(
            f"Target hierarchy: {self.args.target_path}\n"
            f"Source hierarchy: {self.di_container.group_rpath}"
        )
        self.output.print()

        if self.projects.hierarchy_exists(self.args.target_path):
            self.output.warning(
                f"NOTE: Hierarchy already exists at '{self.args.target_path}', would use existing one",
            )
            self.output.print("Actions that would be performed:")
        else:
            self.output.print(
                f"Actions that would be performed:\n1. Create hierarchy group structure at: {self.args.target_path}"
            )

        self._preview_package_forks()
        self.output.print("3. Note: You will need to manually set the following group variables:")
        for variable in self.GROUP_VARIABLES:
            self.output.print(f"   - {variable}")

        return 0

    def _preview_package_forks(self) -> None:
        """Preview package fork operations for dry run."""
        for package_name in CORE_PACKAGES:
            source_package = self.package_service.get_package(package_name)
            if source_package:
                self.output.print(f"2. Fork {package_name} from: {source_package.path_with_namespace}")
                self.output.print(f"   To: {self.args.target_path}/{package_name}")
                default_branch = getattr(source_package, "default_branch", None) or "main (fallback)"
                self.output.print(f"   Default branch: {default_branch}")
            else:
                self.output.warning(f"2. WARNING: {package_name} not found in source hierarchy")
