# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from rich.table import Table

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService


class ListCommand(Command):
    """List all packages"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)

    def execute(self):
        packages = self.package_service.get_all_packages()

        table = Table(title="Packages")
        table.add_column("Name", no_wrap=True)
        table.add_column("Type")
        table.add_column("Enabled")
        table.add_column("Branch")

        rows = []
        for package in packages:
            enabled_status = str(package.builds_access_level)
            if enabled_status.lower() in ["true", "enabled", "public"]:
                enabled_display = f"[green]{enabled_status}[/green]"
            elif enabled_status.lower() in ["false", "disabled", "private"]:
                enabled_display = f"[red]{enabled_status}[/red]"
            else:
                enabled_display = enabled_status

            rows.append(
                (
                    self.package_service.get_display_name(package),
                    self.package_service.pretty_format_ci_path(package),
                    enabled_display,
                    package.default_branch or "-",
                )
            )

        rows.sort(key=lambda row: row[0])
        for row in rows:
            table.add_row(*row)

        self.console.print(table)
        return 0
