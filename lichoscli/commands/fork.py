# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models import Project
from lichoscli.core.services import PackageService
from lichoscli.utils import CI_PKG, CIConfigUtils, HierarchyUtils

logger = logging.getLogger(__name__)


class ForkCommand(Command):
    """Fork a package from source hierarchy to destination namespace

    If no namespace is provided, auto-detects configuration from 00ci:
    - If current 00ci is forked, uses its parent as source and current hierarchy as destination
    - Otherwise, requires explicit namespace parameter
    """

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.projects = self.package_service.get_projects()
        self.source_namespace = None
        self.destination_namespace = None
        self._detect_fork_configuration()

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="package name to fork from base hierarchy")
        sp.add_argument(
            "namespace",
            nargs="?",
            help="destination namespace to fork to (auto-detected if not provided)",
        )

    def validate_args(self) -> None:
        """Validate command-specific arguments."""
        if not self.args.package or not self.args.package.strip():
            raise ValueError("Package name cannot be empty")

        if self.args.namespace and not self.args.namespace.strip():
            raise ValueError("Namespace cannot be empty if provided")

    def execute(self) -> int:
        """Execute the fork command."""
        if self.args.dry:
            return self._dry_run_preview()

        logger.info(
            "Forking package '%s' from '%s' to destination namespace '%s'",
            self.args.package,
            self.source_namespace,
            self.destination_namespace,
        )

        if not self.projects.hierarchy_exists(self.destination_namespace):
            logger.error("Target hierarchy '%s' does not exist", self.destination_namespace)
            return 1

        destination_projects = self.projects.get_projects_for_namespace(self.destination_namespace)
        if not destination_projects:
            logger.error("Cannot access destination hierarchy '%s'", self.destination_namespace)
            return 1

        # Check if 00ci exists in destination namespace
        destination_ci = destination_projects.get(CI_PKG)
        if not destination_ci:
            logger.error(
                "00ci package not found in destination hierarchy '%s'",
                self.destination_namespace,
            )
            return 1

        # Get source projects collection and the base package
        source_projects = self.projects.get_projects_for_namespace(self.source_namespace)
        if not source_projects:
            logger.error("Cannot access source hierarchy '%s'", self.source_namespace)
            return 1

        base_package = source_projects.get(self.args.package)
        if not base_package:
            logger.error(
                "Package '%s' not found in source hierarchy '%s'",
                self.args.package,
                self.source_namespace,
            )
            return 1

        subpath = HierarchyUtils.extract_package_subpath(base_package.path_with_namespace, self.source_namespace)

        # Fork the package to destination namespace with preserved subpath
        forked_package = base_package.fork_to(self.destination_namespace, subpath)
        if not forked_package:
            logger.error(
                "Failed to fork package '%s' to destination namespace",
                self.args.package,
            )
            return 1

        # Configure CI settings to use destination namespace's 00ci
        ci_config_path = self._configure_forked_package_ci(forked_package, destination_projects)

        self.console.print(
            f"[green]Successfully forked package[/green] '{self.args.package}' to '{self.destination_namespace}'"
        )
        self.console.print(f"Forked package CI/CD configured to use: {ci_config_path}")
        return 0

    def _configure_forked_package_ci(self, forked_package: "Project", destination_projects) -> str:
        """Configure CI/CD settings for the forked package to use destination namespace's 00ci.

        Returns:
            The CI config path that was configured.
        """
        package_type = self._determine_package_type(forked_package)
        logger.debug("Detected package type: %s", package_type)

        ci_config_path = CIConfigUtils.get_ci_path(self.destination_namespace, ci_typ=package_type)

        logger.info("Configuring CI/CD to use: %s", ci_config_path)

        updated_package = destination_projects.update(forked_package.name, ci_config_path=ci_config_path)

        if not updated_package:
            logger.warning("Failed to update CI configuration for forked package")

        return ci_config_path

    def _determine_package_type(self, package: "Project") -> str:
        """Determine package type by examining its current CI config, default to gbp."""
        current_ci_path = package.ci_config_path
        if current_ci_path and current_ci_path != ".gitlab-ci.yml":
            parsed = CIConfigUtils.parse_ci_config_path(current_ci_path)
            if parsed and parsed.name:
                logger.debug("Detected package type from CI config: %s", parsed.name)
                return parsed.name

        logger.debug("Could not determine package type, defaulting to gbp")
        return "gbp"

    def _detect_fork_configuration(self):
        """Detect source hierarchy and destination namespace based on 00ci fork status."""
        current_ci = self.package_service.get_package(CI_PKG)

        if self.args.namespace:
            # For explicit namespace, we use current namespace as source
            # and explicit namespace as destination
            self.source_namespace = self.di_container.group_rpath
            self.destination_namespace = self.args.namespace
            logger.debug("Using explicit namespace: %s", self.args.namespace)
            return

        if not current_ci:
            logger.error("No 00ci package found in current hierarchy")
            raise ValueError("Cannot auto-detect configuration without 00ci package")

        if current_ci.is_fork:
            parent_namespace = current_ci.parent_project_namespace
            logger.info("Detected forked 00ci from parent hierarchy: %s", parent_namespace)

            # Source is parent namespace, destination is current namespace
            self.source_namespace = parent_namespace
            self.destination_namespace = self.di_container.group_rpath

            logger.info("Auto-detected fork configuration:")
            logger.info("  Source hierarchy: %s", self.source_namespace)
            logger.info("  Destination: %s", self.destination_namespace)
        else:
            logger.error("Current 00ci is not forked from a parent hierarchy")
            logger.error("Please provide an explicit destination namespace or ensure 00ci is forked")
            raise ValueError("Cannot auto-detect configuration: 00ci is not forked")

    def _dry_run_preview(self) -> int:
        """Show a simple preview of what would be forked."""
        self.console.print("[bold]DRY RUN PREVIEW[/bold]")
        self.console.print(f"Package to fork: [cyan]{self.args.package}[/cyan]")
        self.console.print(f"Source hierarchy: [yellow]{self.source_namespace}[/yellow]")
        self.console.print(f"Destination namespace: [green]{self.destination_namespace}[/green]")

        # Simple validation - just check if basic namespaces exist
        if not self.projects.hierarchy_exists(self.destination_namespace):
            self.console.print(f"[red]ERROR:[/red] Target hierarchy '{self.destination_namespace}' does not exist")
            return 1

        # Get source package to determine package type
        source_projects = self.projects.get_projects_for_namespace(self.source_namespace)
        if not source_projects:
            self.console.print(f"[red]ERROR:[/red] Cannot access source hierarchy '{self.source_namespace}'")
            return 1

        base_package = source_projects.get(self.args.package)
        if not base_package:
            self.console.print(
                f"[red]ERROR:[/red] Package '{self.args.package}' not found in source hierarchy '{self.source_namespace}'"
            )
            return 1

        # Show what CI config would be used
        package_type = self._determine_package_type(base_package)
        ci_config_path = CIConfigUtils.get_ci_path(self.destination_namespace, ci_typ=package_type)
        self.console.print(f"CI/CD would be configured to: [blue]{ci_config_path}[/blue]")

        self.console.print("\n[green]Use without --dry to execute the fork[/green]")
        return 0
