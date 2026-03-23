# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.ui import Cell, Table


class ListCommand(Command):
    """List all packages"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)

    def execute(self):
        packages = self.package_service.get_all_packages()

        rows = []
        for package in packages:
            enabled_status = str(package.builds_access_level)
            normalized = enabled_status.lower()
            if normalized in ["true", "enabled", "public"]:
                enabled_cell = Cell(enabled_status, style="success")
            elif normalized in ["false", "disabled", "private"]:
                enabled_cell = Cell(enabled_status, style="warning")
            else:
                enabled_cell = enabled_status

            rows.append((
                self.package_service.get_display_name(package),
                self.package_service.pretty_format_ci_path(package),
                enabled_cell,
                package.default_branch or "-",
            ))

        rows.sort(key=lambda r: r[0])
        table = Table(title="Packages")
        table.add_column("Name", no_wrap=True)
        table.add_column("Type")
        table.add_column("Enabled")
        table.add_column("Branch")
        for row in rows:
            table.add_row(*row)
        self.output.table(table)
        return 0
