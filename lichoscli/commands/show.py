from datetime import datetime, timezone
from tabulate import tabulate
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils, CIConfigUtils
from dateutil import parser


class ShowCommand(Command):
    """show packages"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.branches = args.branches

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("--branches", action="store_true", help="show branches")

    def execute(self):
        pkg = self.pkg_group_handler.get_package(self.package_name, full_details=True)
        if not pkg:
            print(f"Package '{self.package_name}' not found.")
            return 1
        if self.branches:
            return self.show_branches(pkg)
        else:
            return self.show_package_info(pkg)

    def show_package_info(self, pkg):
        t = [["Setting", "Value"]]
        t.append(["id", pkg.id])
        t.append(["path", pkg.path])
        t.append(["builds_access_level", pkg.builds_access_level])
        t.append(["default_branch", pkg.default_branch])
        if "forked_from_project" in pkg.attributes:
            t.append(
                [
                    "forked_from_project",
                    pkg.attributes["forked_from_project"]["path_with_namespace"],
                ]
            )
        t.append(
            ["ci_config_path", self.pkg_group_handler.pretty_format_ci_path(pkg)]
        )

        print(tabulate(t, headers="firstrow"))

        env = self.pkg_group_handler.get_package_variables(pkg)
        if env:
            print(tabulate([[k, v] for k, v in env.items()], headers=['Variable', 'Value']))

        return 0

    def show_branches(self, pkg):
        branches = pkg.branches.list(all=True)
        if not branches:
            print(f"No branches found for package '{self.package_name}'.")
            return 1

        t = [["SHA", "Age (days)", "Protected", "Name"]]
        now = datetime.now(timezone.utc)

        for branch in branches:
            date_str = branch.commit["committed_date"]
            commit_time = parser.isoparse(date_str)
            age_days = (now - commit_time).days

            t.append([branch.commit["id"][:7], age_days, branch.protected, branch.name])

        print(tabulate(t, headers="firstrow"))
        return 0
