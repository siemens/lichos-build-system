from tabulate import tabulate
from lichoscli.commands.base import Command
from lichoscli.utils import CIConfigUtils


class ListCommand(Command):
    """List all packages"""

    def execute(self):
        headers = ["Name", "Type", "Enabled", "Branch"]
        packages = self.pkg_group_handler.get_all_packages()

        rows = []
        for package in packages:
            if package.namespace["full_path"] is not None and package.namespace["full_path"] != self.pkg_group_handler.group_rpath:
                name = package.namespace["path"] + "/" + package.name
            else:
                name = package.name
            rows.append(
                [
                    name,
                    self.pkg_group_handler.pretty_format_ci_path(package),
                    package.builds_access_level,
                    package.default_branch,
                ]
            )
        rows.sort(key=lambda row: row[0])
        
        print(tabulate(rows, headers=headers))
        return 0
