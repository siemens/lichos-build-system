# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from datetime import datetime, timezone

from dateutil import parser

from lichoscli.commands.base import Command
from lichoscli.core.exceptions import ProviderAPIError
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
from lichoscli.ui import Cell, Table
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class ShowCommand(Command):
    """Show package information and details"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.package_name = BuildUtils.get_package_name(args.package)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("--branches", action="store_true", help="show branches")
        sp.add_argument(
            "--mr",
            action="store_true",
            help="show merge requests for the specified package",
        )
        sp.add_argument("--mr-all", action="store_true", help="show merge requests for all packages")
        sp.add_argument(
            "--dump",
            action="store_true",
            help="dump merge requests as JSON (only with --mr or --mr-all)",
        )

    def execute(self):
        if self.args.mr_all:
            return self.list_all_merge_requests()
        if self.args.mr:
            if not self.package_name:
                self.output.error("Error: Package name required with --mr flag")
                return 1
            return self.list_package_merge_requests()

        if not self.package_name:
            self.output.error("Error: Package name required")
            return 1

        pkg = self.package_service.get_package(self.package_name)
        if not pkg:
            self.output.error(f"Package '{self.package_name}' not found.")
            return 1

        if self.args.branches:
            return self.show_branches(pkg)
        return self.show_package_info(pkg)

    def show_package_info(self, pkg):
        settings = [
            ("id", str(pkg.id)),
            ("path", pkg.path),
            ("builds_access_level", pkg.builds_access_level),
            ("ci_config_path", pkg.ci_config_path),
            ("default_branch", pkg.default_branch),
        ]

        if "forked_from_project" in pkg.attributes:
            settings.append(
                (
                    "forked_from_project",
                    pkg.attributes["forked_from_project"]["path_with_namespace"],
                )
            )

        variable_rows: list[list[str]] = []

        try:
            variables = pkg.variables.list()
            if variables:
                for var in variables:
                    inherited_icon = "Inherited" if var.inherited else "Project Level"
                    variable_rows.append(
                        [
                            var.variable_type,
                            var.key,
                            var.value,
                            str(var.masked),
                            str(var.protected),
                            str(var.masked),
                            str(var.raw),
                            var.environment_scope or "*",
                            inherited_icon,
                            var.description or "",
                        ]
                    )
        except ProviderAPIError as e:
            self.output.warning(f"Warning: Could not fetch variables: {e}")

        info_table = Table(title="Package Information: {0}".format(pkg.name))
        info_table.add_column("Setting", no_wrap=True)
        info_table.add_column("Value")
        for setting, value in settings:
            info_table.add_row(setting, value)
        self.output.table(info_table)

        if variable_rows:
            self.output.print()
            var_table = Table(title="Variables")
            var_table.add_column("Type", no_wrap=True)
            var_table.add_column("Key", no_wrap=True)
            var_table.add_column("Value")
            var_table.add_column("Hidden", no_wrap=True)
            var_table.add_column("Protected", no_wrap=True)
            var_table.add_column("Masked", no_wrap=True)
            var_table.add_column("Raw", no_wrap=True)
            var_table.add_column("Scope", no_wrap=True)
            var_table.add_column("Level", no_wrap=True)
            var_table.add_column("Description")
            for row in variable_rows:
                var_table.add_row(*row)
            self.output.table(var_table)

        return 0

    def show_branches(self, pkg):
        branches = pkg.branches.list(all=True)
        if not branches:
            self.output.warning(f"No branches found for package '{self.package_name}'.")
            return 1

        now = datetime.now(timezone.utc)
        rows = []

        for branch in branches:
            date_str = branch.commit["committed_date"]
            commit_time = parser.isoparse(date_str)
            age_days = (now - commit_time).days

            author_name = branch.commit.get("author_name", "Unknown")
            rows.append(
                [
                    branch.commit["id"][:7],
                    str(age_days),
                    Cell("yes", style="warning") if branch.protected else "",
                    author_name,
                    branch.name,
                ]
            )

        branches_table = Table(title="Branches for {0}".format(pkg.name))
        branches_table.add_column("SHA", no_wrap=True)
        branches_table.add_column("Age (days)", justify="right", no_wrap=True)
        branches_table.add_column("Protected", no_wrap=True)
        branches_table.add_column("Created by")
        branches_table.add_column("Name")
        for row in rows:
            branches_table.add_row(*row)
        self.output.table(branches_table)
        return 0

    def list_package_merge_requests(self):
        """List merge requests for a specific package"""
        try:
            package = self.package_service.get_package(self.package_name)
            if not package:
                self.output.error(f"Package '{self.package_name}' not found")
                return 1

            merge_requests = self._get_merge_requests_for_package(package)

            if not merge_requests:
                self.output.warning(
                    f"No open merge requests found for package '{self.package_name}'",
                )
                return 0

            self._display_merge_requests([(package.name, merge_requests)])
            return 0

        except ProviderAPIError as e:
            logger.error("GitLab API error: %s", str(e))
            self.output.error(f"GitLab API error: {e}")
            return 1

    def list_all_merge_requests(self):
        """List merge requests for all packages"""
        try:
            packages = self.package_service.get_all_packages()

            results = []
            total_mrs = 0

            for package in packages:
                try:
                    merge_requests = self._get_merge_requests_for_package(package)
                    if merge_requests:
                        results.append((package.name, merge_requests))
                        total_mrs += len(merge_requests)
                except ProviderAPIError as e:
                    logger.warning(
                        "Failed to get merge requests for package %s: %s",
                        package.name,
                        str(e),
                    )

            if not results:
                self.output.warning("No open merge requests found in any package")
                return 0

            self.output.accent(
                f"Found {total_mrs} open merge request(s) across {len(results)} package(s):",
            )
            self.output.print()
            self._display_merge_requests(results)
            return 0

        except ProviderAPIError as e:
            logger.error("Error listing merge requests: %s", str(e))
            self.output.error(f"Error listing merge requests: {e}")
            return 1

    def _get_merge_requests_for_package(self, package):
        try:
            return package.merge_requests.list(state="opened", get_all=True)
        except ProviderAPIError as e:
            logger.debug("Failed to get merge requests for package %s: %s", package.name, str(e))
            return []

    def _display_merge_requests(self, results):
        if self.args.dump:
            output = []
            for package_name, merge_requests in results:
                for mr in merge_requests:
                    output.append(
                        {
                            "package": package_name,
                            "iid": mr.iid,
                            "title": mr.title,
                            "source_branch": mr.source_branch,
                            "target_branch": mr.target_branch,
                            "created_at": mr.created_at,
                            "web_url": mr.web_url,
                        }
                    )
            self.output.json(output)
        else:
            package_rows = []
            for package_name, merge_requests in results:
                package_obj = self.package_service.get_package(package_name)
                display_name = package_name
                if (
                    package_obj
                    and package_obj.namespace["full_path"] is not None
                    and package_obj.namespace["full_path"] != self.di_container.group_rpath
                ):
                    display_name = package_obj.namespace["path"] + "/" + package_name

                if "/" in display_name:
                    display_name = display_name.split("/")[-1]

                package_rows.append(
                    (
                        display_name,
                        [
                            [
                                f"#{mr.iid}",
                                self._format_date_with_year(mr.created_at),
                                mr.author["name"],
                                mr.source_branch,
                                mr.target_branch,
                                mr.title,
                                mr.web_url,
                            ]
                            for mr in merge_requests
                        ],
                    )
                )
            for package_name, rows in package_rows:
                mr_count = len(rows)
                suffix = "s" if mr_count != 1 else ""
                mr_table = Table(title="{0} ({1} MR{2})".format(package_name, mr_count, suffix))
                mr_table.add_column("ID", no_wrap=True)
                mr_table.add_column("Created", no_wrap=True)
                mr_table.add_column("Author", no_wrap=True)
                mr_table.add_column("Source", no_wrap=True)
                mr_table.add_column("Target", no_wrap=True)
                mr_table.add_column("Title")
                mr_table.add_column("URL")
                for row in rows:
                    mr_table.add_row(*row)
                self.output.table(mr_table)
                self.output.print()

    def _format_date_with_year(self, date_str):
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%y")
        except (ValueError, AttributeError):
            return date_str or "-"
