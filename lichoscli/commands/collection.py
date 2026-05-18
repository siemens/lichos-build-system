# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
from pathlib import Path

from git.exc import GitCommandError
from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.config import UserConfigStore
from lichoscli.core.di import DIContainer
from lichoscli.core.handlers.lichos_anchor import LichosAnchorHandler
from lichoscli.core.models.git.git_url import GitUrl
from lichoscli.core.services import PackageService, PkgGroupDiscoveryService
from lichoscli.utils import CI_PKG, CORE_PACKAGES

logger = logging.getLogger(__name__)

_SEARCH_QUERY = "00ci"


class CollectionCommand(Command):
    """Manage collections (create or clone)"""

    GROUP_VARIABLES = [
        "PROD_NEXUS_AUTH (masked, protected)",
        "RMS_PLATFORM_TOKEN (masked, protected)",
    ]

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.lichos_anchor_handler = di_container.obtain_ref(LichosAnchorHandler)

    @classmethod
    def add_arguments(cls, sp):
        subparsers = sp.add_subparsers(dest="action", help="collection actions")

        create_parser = subparsers.add_parser(
            "create",
            help="create a new collection by forking core packages to a target path",
        )
        create_parser.add_argument(
            "target",
            help="target path for the new collection (e.g., 'mygroup/mydistro')",
        )

        clone_parser = subparsers.add_parser(
            "clone",
            help="create a .lichos anchor file; pass --all to also clone all packages",
        )
        clone_parser.add_argument(
            "target",
            nargs="?",
            default=None,
            help="distribution URL to clone from",
        )
        clone_parser.add_argument(
            "directory",
            nargs="?",
            default=None,
            help="local directory name (default: last component of the URL path)",
        )
        clone_parser.add_argument(
            "--all",
            dest="clone_all",
            action="store_true",
            help="clone all packages in the collection in addition to writing the anchor file",
        )

    def validate_args(self) -> None:
        if self.args.action == "clone" and self.args.target and not getattr(self.args, "branch_explicitly_provided", False):
            raise ValueError("--branch is required for 'collection clone'")

    def execute(self) -> int:
        if not self.args.action:
            logger.error("No action specified. Use 'collection create' or 'collection clone'.")
            return 1

        action_name = self.args.action.replace("-", "_")
        action_method = getattr(self, "action_{}".format(action_name), None)
        if action_method and callable(action_method):
            return action_method()

        logger.error("Unknown action: %s", self.args.action)
        return 1

    def action_create(self) -> int:
        logger.info(
            "Creating collection at '%s' based on current hierarchy '%s'",
            self.args.target,
            self.di_container.group_rpath,
        )

        if self.args.dry:
            logger.info("DRY RUN: Would create hierarchy with the following configuration:")
            return self._create_dry_run_preview()

        pkg_group_discovery = self.di_container.obtain_ref(PkgGroupDiscoveryService)
        if pkg_group_discovery.exists(self.args.target, CI_PKG, host=self.di_container.host):
            logger.info(
                "Hierarchy already exists at '%s', using existing one",
                self.args.target,
            )
        else:
            self._create_target_hierarchy()

        if not self._fork_required_packages():
            logger.error("Failed to fork required packages")
            return 1

        logger.info("Successfully created hierarchy at '%s'", self.args.target)
        self.output.warning("IMPORTANT: You must manually set the following group variables:")
        for variable in self.GROUP_VARIABLES:
            self.output.print("  - {}".format(variable))
        self.output.print("  - CI_00CI_PROJECT_PATH: {}/{}".format(self.args.target, CI_PKG))
        package_service = self.di_container.obtain_ref(PackageService)
        target_projects = package_service.get_projects().get_projects_for_namespace(self.args.target)
        if target_projects:
            logger.info("Hierarchy created successfully at: %s", self.args.target)
        return 0

    def action_clone(self) -> int:
        """Clone a distribution: write .lichos anchor and optionally clone packages."""
        if self.args.target:
            return self._clone_from_url()
        return self._list_available_groups()

    def _clone_from_url(self) -> int:
        """Clone using a provided URL: create collection directory, write anchor."""
        host, pkg_group = GitUrl.parse_group_url(self.args.target)
        if not pkg_group:
            logger.error("Could not parse group path from: %s", self.args.target)
            return 1

        host = self._apply_remote_context(url_host=host, pkg_group=pkg_group)
        if not host:
            return 1

        collection_dir = self.args.directory or pkg_group.split("/")[-1]
        collection_path = Path(collection_dir)

        if self.args.dry:
            self.output.accent("DRY RUN PREVIEW:")
            self.output.print("Would create directory: {}".format(collection_dir))
            self.output.print("Would write .lichos anchor: host={}, pkg_group={}".format(host, pkg_group))
            if self.args.clone_all:
                self.output.print("Would clone all packages")
            return 0

        collection_path.mkdir(parents=True, exist_ok=True)
        self.lichos_anchor_handler.write(
            host=host, pkg_group=pkg_group, branch=self.args.branch, target_dir=collection_path
        )
        self.output.success(
            "Initialized lichos collection in '{}' (host={}, pkg_group={})".format(collection_dir, host, pkg_group)
        )

        if self.args.clone_all:
            return self._clone_all_packages(collection_path)
        return 0

    def _list_available_groups(self) -> int:
        """List available distributions on the configured GitLab instance."""
        host = self._apply_remote_context()
        if not host:
            return 1

        pkg_group_discovery = self.di_container.obtain_ref(PkgGroupDiscoveryService)
        self.output.info("Searching for distributions on {}...".format(host))
        groups = pkg_group_discovery.search_pkg_groups(_SEARCH_QUERY, host=host)
        if not groups:
            self.output.warning(
                "No lichos collections matching '{}' found on {}.".format(_SEARCH_QUERY, host)
            )
            return 0

        self.output.print("Available lichos collections on {}:".format(host))
        for group in groups:
            self.output.print("  {}".format(group))
        return 0

    def _clone_all_packages(self, collection_path: Path) -> int:
        """Clone all packages into the distro directory."""
        package_service = self.di_container.obtain_ref(PackageService)
        packages = package_service.get_all_packages()
        if not packages:
            logger.error("No packages found in distribution")
            return 1

        for pkg in packages:
            target_dir = str(collection_path / pkg.name)
            if os.path.exists(target_dir):
                logger.info("Skipping '%s': directory already exists", pkg.name)
                continue
            clone_url = pkg.ssh_url_to_repo
            try:
                if self.args.branch:
                    Repo.clone_from(clone_url, target_dir, branch=self.args.branch)
                else:
                    Repo.clone_from(clone_url, target_dir, branch=pkg.default_branch)
                logger.info("Cloned '%s'", pkg.name)
            except GitCommandError:
                if self.args.branch:
                    logger.warning(
                        "Branch '%s' not found for '%s', falling back to default branch '%s'",
                        self.args.branch, pkg.name, pkg.default_branch,
                    )
                    Repo.clone_from(clone_url, target_dir, branch=pkg.default_branch)
                else:
                    raise
        return 0

    def _apply_remote_context(self, url_host=None, pkg_group=None):
        """Resolve host and apply remote context to the container."""
        host = url_host or self.di_container.host
        if not host:
            config = UserConfigStore.read()
            host = config.get("host")
        if not host:
            logger.error(
                "No GitLab host configured. "
                "Please specify --host or run 'lichoscli setup'."
            )
            return None
        self.di_container.host = host
        if pkg_group:
            self.di_container.group_rpath = pkg_group
        return host

    def _create_target_hierarchy(self) -> bool:
        """Create the target group structure for the new distro."""
        path_parts: list[str] = self.args.target.split("/")
        current_path = ""

        for i, part in enumerate(path_parts):
            if i == 0:
                current_path = part
            else:
                current_path = "{}/{}".format(current_path, part)

            package_service = self.di_container.obtain_ref(PackageService)
            existing_projects = package_service.get_projects().get_projects_for_namespace(current_path)
            if existing_projects:
                logger.debug("Group '%s' already exists", current_path)
                continue

            parent_path = "/".join(path_parts[:i]) if i > 0 else None
            parent_id = None
            pkg_group_discovery = self.di_container.obtain_ref(PkgGroupDiscoveryService)
            if parent_path:
                parent_id = pkg_group_discovery.get_group_id(parent_path)

            logger.info("Creating group: %s", current_path)
            pkg_group_discovery.create_group(
                name=part,
                path=part,
                parent_id=parent_id,
                description="Auto-created collection group: {}".format(part),
            )
        return True

    def _fork_required_packages(self) -> bool:
        """Fork required packages to target hierarchy."""
        package_service = self.di_container.obtain_ref(PackageService)
        for package_name in CORE_PACKAGES:
            source_package = package_service.get_package(package_name)
            if not source_package:
                logger.warning("Package '%s' not found in source hierarchy, skipping", package_name)
                continue

            logger.info("Forking package '%s' to target hierarchy", package_name)
            forked_package = source_package.fork_to(self.args.target)

            if not forked_package:
                logger.error("Failed to fork package '%s'", package_name)
                return False

            logger.debug(
                "Successfully forked package '%s' to '%s'",
                package_name,
                forked_package.path_with_namespace,
            )
        return True

    def _create_dry_run_preview(self) -> int:
        """Preview what would be done by 'hierarchy create' in a dry run."""
        self.output.accent("DRY RUN PREVIEW:")
        self.output.print(
            "Target hierarchy: {}\nSource hierarchy: {}".format(
                self.args.target,
                self.di_container.group_rpath,
            )
        )
        self.output.print()

        pkg_group_discovery = self.di_container.obtain_ref(PkgGroupDiscoveryService)
        if pkg_group_discovery.exists(self.args.target, CI_PKG, host=self.di_container.host):
            self.output.warning(
                "NOTE: Hierarchy already exists at '{}', would use existing one".format(
                    self.args.target
                ),
            )
            self.output.print("Actions that would be performed:")
        else:
            self.output.print(
                "Actions that would be performed:\n1. Create hierarchy group structure at: {}".format(
                    self.args.target
                )
            )

        self._preview_package_forks()
        self.output.print("3. Note: You will need to manually set the following group variables:")
        for variable in self.GROUP_VARIABLES:
            self.output.print("   - {}".format(variable))

        return 0

    def _preview_package_forks(self) -> None:
        """Preview package fork operations for dry run."""
        package_service = self.di_container.obtain_ref(PackageService)
        for package_name in CORE_PACKAGES:
            source_package = package_service.get_package(package_name)
            if source_package:
                self.output.print(
                    "2. Fork {} from: {}".format(package_name, source_package.path_with_namespace)
                )
                self.output.print(
                    "   To: {}/{}".format(self.args.target, package_name)
                )
                default_branch = source_package.default_branch or "main (fallback)"
                self.output.print("   Default branch: {}".format(default_branch))
            else:
                self.output.warning("2. WARNING: {} not found in source hierarchy".format(package_name))
