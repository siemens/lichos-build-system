import logging
from datetime import datetime, timezone

from dateutil import parser
from gitlab.exceptions import GitlabError
from rich.panel import Panel
from rich.table import Table

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
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
                self.console.print("[red]Error: Package name required with --mr flag[/red]")
                return 1
            return self.list_package_merge_requests()

        if not self.package_name:
            self.console.print("[red]Error: Package name required[/red]")
            return 1

        pkg = self.package_service.get_package(self.package_name)
        if not pkg:
            self.console.print(f"[red]Package '{self.package_name}' not found.[/red]")
            return 1

        if self.args.branches:
            return self.show_branches(pkg)
        return self.show_package_info(pkg)

    def show_package_info(self, pkg):
        table = Table(
            title=f"Package Information: {pkg.name}",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Setting", style="cyan", width=20)
        table.add_column("Value", style="white")

        table.add_row("id", str(pkg.id))
        table.add_row("path", pkg.path)
        table.add_row("builds_access_level", pkg.builds_access_level)
        table.add_row(
            "ci_config_path",
            self.package_service.pretty_format_ci_path(pkg),
        )
        table.add_row("default_branch", pkg.default_branch)

        if "forked_from_project" in pkg.attributes:
            table.add_row(
                "forked_from_project",
                pkg.attributes["forked_from_project"]["path_with_namespace"],
            )

        self.console.print(table)
        self.console.print()

        try:
            variables = pkg.variables.list()
            if variables:
                var_table = Table(title="Variables", show_header=True, header_style="bold cyan")
                var_table.add_column("Type", style="green")
                var_table.add_column("Key", style="yellow")
                var_table.add_column("Value", style="white")
                var_table.add_column("Hidden", style="red")
                var_table.add_column("Protected", style="blue")
                var_table.add_column("Masked", style="red")
                var_table.add_column("Raw", style="dim")
                var_table.add_column("Scope", style="magenta")
                var_table.add_column("Level", style="orange1")
                var_table.add_column("Description", style="dim")

                for var in variables:
                    inherited_icon = "Inherited" if var.inherited else "Project Level"
                    var_table.add_row(
                        var.variable_type,
                        var.key,
                        var.value,
                        str(var.masked),  # 'masked' is the GitLab API term for 'hidden'
                        str(var.protected),
                        str(var.masked),
                        str(var.raw),
                        var.environment_scope or "*",
                        inherited_icon,
                        var.description or "",
                    )

                self.console.print(var_table)
        except GitlabError as e:
            self.console.print(f"[yellow]Warning: Could not fetch variables: {e}[/yellow]")

        return 0

    def show_branches(self, pkg):
        branches = pkg.branches.list(all=True)
        if not branches:
            self.console.print(f"[yellow]No branches found for package '{self.package_name}'.[/yellow]")
            return 1

        table = Table(
            title=f"Branches for {pkg.name}",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("SHA", style="cyan", width=8)
        table.add_column("Age (days)", style="yellow", justify="right")
        table.add_column("Protected", style="red", justify="center")
        table.add_column("Created by", style="green")
        table.add_column("Name", style="white")

        now = datetime.now(timezone.utc)

        for branch in branches:
            date_str = branch.commit["committed_date"]
            commit_time = parser.isoparse(date_str)
            age_days = (now - commit_time).days

            # Get the author of the last commit on the branch
            author_name = branch.commit.get("author_name", "Unknown")

            protected_icon = "🔒" if branch.protected else ""

            table.add_row(
                branch.commit["id"][:7],
                str(age_days),
                protected_icon,
                author_name,
                branch.name,
            )

        self.console.print(table)
        return 0

    def list_package_merge_requests(self):
        """List merge requests for a specific package"""
        try:
            package = self.package_service.get_package(self.package_name)
            if not package:
                self.console.print(f"[red]Package '{self.package_name}' not found[/red]")
                return 1

            merge_requests = self._get_merge_requests_for_package(package)

            if not merge_requests:
                self.console.print(f"[yellow]No open merge requests found for package '{self.package_name}'[/yellow]")
                return 0

            self._display_merge_requests([(package.name, merge_requests)])
            return 0

        except GitlabError as e:
            logger.error("GitLab API error: %s", str(e))
            self.console.print(f"[red]GitLab API error: {e}[/red]")
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
                except GitlabError as e:
                    logger.warning(
                        "Failed to get merge requests for package %s: %s",
                        package.name,
                        str(e),
                    )

            if not results:
                self.console.print("[yellow]No open merge requests found in any package[/yellow]")
                return 0

            self.console.print(f"Found {total_mrs} open merge request(s) across {len(results)} package(s):")
            self.console.print()
            self._display_merge_requests(results)
            return 0

        except GitlabError as e:
            logger.error("Error listing merge requests: %s", str(e))
            self.console.print(f"[red]Error listing merge requests: {e}[/red]")
            return 1

    def _get_merge_requests_for_package(self, package):
        try:
            return package.merge_requests.list(state="opened", get_all=True)
        except GitlabError as e:
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
            self.console.print_json(data=output)
        else:
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

                self.console.print(
                    f"\n[bold bright_blue] {display_name}[/bold bright_blue] [dim]({len(merge_requests)} MR{'s' if len(merge_requests) > 1 else ''})[/dim]"
                )
                self.console.print("─" * 80, style="bright_blue")

                for i, mr in enumerate(merge_requests, 1):
                    created_date = self._format_date_with_year(mr.created_at)

                    mr_table = Table(show_header=False, box=None, padding=(0, 1))
                    mr_table.add_column("Field", style="dim", width=12)
                    mr_table.add_column("Value", style="white")
                    mr_table.add_row("ID:", f"[bold cyan]#{mr.iid}[/bold cyan]")
                    mr_table.add_row("Created:", f"[dim]{created_date}[/dim]")
                    mr_table.add_row("Author:", f"[green]{mr.author['name']}[/green]")
                    mr_table.add_row(
                        "Branches:",
                        f"[yellow]{mr.source_branch}[/yellow] → [cyan]{mr.target_branch}[/cyan]",
                    )
                    mr_table.add_row("Title:", f"[white]{mr.title}[/white]")
                    mr_table.add_row("URL:", f"[blue underline]{mr.web_url}[/blue underline]")

                    panel = Panel(
                        mr_table,
                        title=f"[bold white]MR {i}/{len(merge_requests)}[/bold white]",
                        border_style="blue",
                        padding=(0, 1),
                    )
                    self.console.print(panel)
                    if i < len(merge_requests):
                        self.console.print()
                self.console.print()

    def _format_date_with_year(self, date_str):
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%y")
        except (ValueError, AttributeError):
            return date_str or "-"
