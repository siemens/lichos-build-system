# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProjectFetchingError
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class ConfigureCommand(Command):
    """Configure project settings (fork relationships, branch protection)"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        actions = sp.add_subparsers(dest="configure_action", title="settings")
        actions.required = True

        # --- fork ---
        fork_parser = actions.add_parser("fork", help="manage fork relationships")
        fork_actions = fork_parser.add_subparsers(dest="fork_action", title="fork actions")
        fork_actions.required = True

        fork_set = fork_actions.add_parser("set", help="set fork relationship to a parent package")
        fork_set.add_argument("package", help="package to configure")
        fork_set.add_argument("parent", help="parent package to fork from")

        fork_unset = fork_actions.add_parser("unset", help="remove fork relationship")
        fork_unset.add_argument("package", help="package to configure")

        # --- forcepush ---
        fp_parser = actions.add_parser("forcepush", help="toggle force-push on a protected branch")
        fp_actions = fp_parser.add_subparsers(dest="forcepush_action", title="forcepush actions")
        fp_actions.required = True

        fp_enable = fp_actions.add_parser("enable", help="allow force-push on branch")
        fp_enable.add_argument("package", help="package to configure")

        fp_disable = fp_actions.add_parser("disable", help="disallow force-push on branch")
        fp_disable.add_argument("package", help="package to configure")

    def validate_args(self) -> None:
        if self.args.configure_action == "forcepush" and self.args.branch is None:
            raise ValueError("--branch is required for forcepush configuration")

    def execute(self) -> int:
        action = self.args.configure_action
        if action == "fork":
            if self.args.fork_action == "set":
                return self._handle_fork_set()
            return self._handle_fork_unset()
        if action == "forcepush":
            if self.args.forcepush_action == "enable":
                return self._handle_forcepush(enabled=True)
            return self._handle_forcepush(enabled=False)
        return 1

    def _resolve_package(self, package_arg):
        """Resolve and fetch a package by name, returning None on failure."""
        pn = BuildUtils.get_package_name(package_arg)
        if not pn:
            logger.error("Invalid package name: %s", package_arg)
            return None
        pkg = self.package_service.get_package(pn)
        if pkg is None:
            logger.error("Package not found: %s", pn)
        return pkg

    def _handle_fork_set(self) -> int:
        pkg = self._resolve_package(self.args.package)
        if pkg is None:
            return 1

        parent_arg = self.args.parent
        if BuildUtils.is_web_url(parent_arg):
            parent_pkg = self.package_service.get_project_by_url(parent_arg)
            if parent_pkg is None:
                logger.error("Could not resolve parent project from URL: %s", parent_arg)
                return 1
        else:
            parent_pkg = self.package_service.get_package(parent_arg)
            if parent_pkg is None:
                logger.error("Parent package not found: %s", parent_arg)
                return 1

        try:
            pkg.create_fork_relation(parent_pkg.id)
        except ProjectFetchingError as e:
            logger.error("Failed to set fork relation on %s: %s", self.args.package, e)
            return 1

        logger.info(
            "Fork relationship set: %s -> %s",
            self.args.package,
            self.args.parent,
        )
        return 0

    def _handle_fork_unset(self) -> int:
        pkg = self._resolve_package(self.args.package)
        if pkg is None:
            return 1

        if not pkg.is_fork:
            logger.warning(
                "Package '%s' does not have an active fork relationship; proceeding anyway",
                self.args.package,
            )

        try:
            pkg.delete_fork_relation()
        except ProjectFetchingError as e:
            logger.error("Failed to remove fork relation on %s: %s", self.args.package, e)
            return 1

        logger.info("Fork relationship removed from %s", self.args.package)
        return 0

    def _handle_forcepush(self, enabled: bool) -> int:
        pkg = self._resolve_package(self.args.package)
        if pkg is None:
            return 1

        success = pkg.set_force_push(self.args.branch, enabled)
        if not success:
            logger.error(
                "Failed to %s force-push on branch '%s' for package '%s'",
                "enable" if enabled else "disable",
                self.args.branch,
                self.args.package,
            )
            return 1

        logger.info(
            "Force-push %s on branch '%s' for package '%s'",
            "enabled" if enabled else "disabled",
            self.args.branch,
            self.args.package,
        )
        return 0
