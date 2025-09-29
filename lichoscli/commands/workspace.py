import logging
import os
import subprocess
from typing import List, Optional

from prompt_toolkit.shortcuts import checkboxlist_dialog, radiolist_dialog
from rich import box
from rich.prompt import Confirm
from rich.table import Table

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.services import DependencyService, PackageService, WorkspaceService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class WorkspaceCommand(Command):
    """Manage LiChOS workspaces with branch context and dependent packages"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.workspace_service = di_container.obtain_ref(WorkspaceService)
        self.package_service = di_container.obtain_ref(PackageService)
        self.dependency_service = di_container.obtain_ref(DependencyService)
        self.package_name = BuildUtils.get_package_name(args.package)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument(
            "action",
            help="action to perform",
            choices=[
                "create",
                "enter",
                "list",
                "delete",
                "show",
                "add-package",
                "remove-package",
            ],
        )
        sp.add_argument("package", nargs="?", help="package name to add/remove")

    def action_create(self):
        """Create a new workspace."""

        if not self.args.branch:
            logger.error("Branch name is required for create action")
            return 1

        package_name = BuildUtils.get_package_name(self.args.package)

        if not package_name:
            logger.error("Package name is required for create action")
            return 1

        package = self.package_service.get_package(package_name)
        if not package:
            logger.error("Package '%s' not found", package_name)
            return 1

        all_packages = self.package_service.get_all_packages()

        # Build DAG to get reverse dependencies efficiently
        logger.info("Building dependency DAG for reverse dependency analysis")
        dag = self.dependency_service.build_dependency_dag(
            all_packages, package.default_branch, wait_for_completion=False
        )

        reverse_deps = dag.get_reverse_deps(package.name)

        package_names_to_add = [package_name]

        if not reverse_deps:
            self.console.print(
                f"[yellow]No reverse dependencies found for package '[cyan]{package_name}[/cyan]'[/yellow]"
            )

        else:
            selected_deps = self._select_reverse_dependencies(package_name, reverse_deps, dag)
            if selected_deps is None:
                self.console.print("[yellow]Workspace creation cancelled[/yellow]")
                return 0

            package_names_to_add.extend(selected_deps)

        try:
            workspace = self.workspace_service.create_workspace(self.args.branch, package_names_to_add)
            self.console.print(f"[green]✓ Created workspace with branch '[cyan]{self.args.branch}[/cyan]'[/green]")
            self.console.print(
                f"[green]✓ Added packages:[/green] [cyan]{', '.join([pkg.name for pkg in workspace.packages])}[/cyan]"
            )
            return 0
        except ValueError as e:
            logger.error("Failed to create workspace: %s", e)
            return 1

    def action_enter(self):
        """Enter the workspace with the specified branch."""

        branch_name = self.args.branch
        workspaces = []
        if self.package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(self.package_name)
        else:
            workspaces = self.workspace_service.list_workspaces()

        if not workspaces:
            logger.error("No workspaces available to enter")
            return 1

        choices = []
        for workspace in workspaces:
            choice_text = workspace.name
            if workspace.packages:
                package_names = [pkg.name for pkg in workspace.packages]
                choice_text += f" [{', '.join(package_names)}]"
            choices.append((workspace.name, choice_text))

        self.console.print("\n[bold]Select workspace to enter:[/bold]")
        try:
            branch_name = radiolist_dialog(
                title="Choose workspace:",
                text="Select a workspace to enter:",
                values=choices,
            ).run()

            if branch_name is None:
                self.console.print("[yellow]Workspace selection cancelled[/yellow]")
                return 0
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Workspace selection cancelled[/yellow]")
            return 0

        os.environ["LICHOS_BRANCH"] = branch_name
        self.console.print(f"[green]Entering workspace '[cyan]{branch_name}[/cyan]'[/green]")

        r = subprocess.run([os.environ.get("SHELL", "/bin/sh")], check=False)
        return r.returncode

    def action_list(self):
        """List all workspaces."""

        workspaces = []
        if self.package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(self.package_name)
        else:
            workspaces = self.workspace_service.list_workspaces()

        if not workspaces:
            self.console.print("[yellow]No workspaces found[/yellow]")
            return 0

        current_workspace = self.workspace_service.get_current_workspace()
        current_name = current_workspace.name if current_workspace else None

        self.console.print("\n[bold]Available workspaces:[/bold]")
        for workspace in workspaces:
            indicator = " [green](current)[/green]" if workspace.name == current_name else ""

            if workspace.packages:
                package_names = [pkg.name for pkg in workspace.packages]
                packages_info = f" [dim]\\[{', '.join(package_names)}][/dim]"
            else:
                packages_info = ""

            self.console.print(f"  [cyan]{workspace.name}[/cyan]{packages_info}{indicator}")

        return 0

    def action_delete(self):
        """Delete a workspace."""
        branch = self.args.branch

        if self.args.branch and self.args.branch_explicitly_provided:
            workspace = self.workspace_service.get_workspace(branch)
            if not workspace:
                logger.error("Workspace with branch '%s' does not exist", branch)
                return 1
            if self.workspace_service.delete_workspace(branch):
                self.console.print(f"[green]✓ Deleted workspace with branch '[cyan]{branch}[/cyan]'[/green]")
                return 0
        workspaces = []
        if self.package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(self.package_name)
        else:
            workspaces = self.workspace_service.list_workspaces()

        if not workspaces:
            self.console.print("[yellow]No workspaces available to delete[/yellow]")
            return 0

        choices = []
        for workspace in workspaces:
            choice_text = workspace.name
            if workspace.packages:
                package_names = [pkg.name for pkg in workspace.packages]
                choice_text += f" [{', '.join(package_names)}]"
            choices.append((workspace.name, choice_text))

        self.console.print("\n[bold]Select workspace to delete:[/bold]")
        try:
            branch = radiolist_dialog(
                title="Choose workspace to delete:",
                text="Select a workspace to delete:",
                values=choices,
            ).run()

            if branch is None:
                self.console.print("[yellow]Workspace deletion cancelled[/yellow]")
                return 0
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Workspace deletion cancelled[/yellow]")
            return 0

        if not Confirm.ask(
            f"Are you sure you want to delete workspace '[cyan]{branch}[/cyan]'?",
            default=False,
        ):
            self.console.print("[yellow]Workspace deletion cancelled[/yellow]")
            return 0

        if self.workspace_service.delete_workspace(branch):
            self.console.print(f"[green]✓ Deleted workspace with branch '[cyan]{branch}[/cyan]'[/green]")
            return 0
        logger.error("Workspace with branch '%s' does not exist", branch)
        return 1

    def action_show(self):
        """Show workspace details."""
        branch = self.args.branch
        if not branch:
            current_workspace = self.workspace_service.get_current_workspace()
            if current_workspace:
                branch = current_workspace.name
            else:
                logger.error("No branch name provided and no current workspace")
                return 1

        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        self.console.print(f"\n[bold]Workspace:[/bold] [cyan]{workspace.name}[/cyan]")

        package_count = len(workspace.packages) if workspace.packages else 0
        self.console.print(f"[bold]Packages:[/bold] {package_count}")

        if workspace.packages:
            for package in workspace.packages:
                self.console.print(f"  • [cyan]{package.name}[/cyan]")
        else:
            self.console.print("[yellow]No packages in workspace[/yellow]")

        return 0

    def action_add_package(self):
        """Add a package to a workspace."""
        branch = self.args.branch
        package_name = self.args.package

        if not branch:
            logger.error("Branch name is required")
            return 1

        if not package_name:
            logger.error("Package name is required")
            return 1

        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        resolved_package = BuildUtils.get_package_name(package_name)

        package = self.package_service.get_package(resolved_package)
        if not package:
            logger.error("Package '%s' not found", resolved_package)
            return 1

        all_packages = self.package_service.get_all_packages()

        # Build DAG to get reverse dependencies efficiently
        logger.info("Building dependency DAG for reverse dependency analysis")
        dag = self.dependency_service.build_dependency_dag(all_packages, self.args.branch, wait_for_completion=False)

        # Get reverse dependencies using the centralized method
        reverse_deps = dag.get_reverse_deps(package.name)

        packages_to_add = [resolved_package]

        if reverse_deps:
            selected_deps = self._select_reverse_dependencies(resolved_package, reverse_deps, dag)

            if selected_deps is None:
                self.console.print("[yellow]Package addition cancelled[/yellow]")
                return 0

            packages_to_add.extend(selected_deps)
        else:
            self.console.print(
                f"[yellow]No reverse dependencies found for package '[cyan]{resolved_package}[/cyan]'[/yellow]"
            )

        added_packages = []
        for pkg_name in packages_to_add:
            if self.workspace_service.add_package_to_workspace(branch, pkg_name):
                added_packages.append(pkg_name)

        if added_packages:
            self.console.print(
                f"[green]✓ Added packages to workspace with branch '[cyan]{branch}[/cyan]':[/green] [cyan]{', '.join(added_packages)}[/cyan]"
            )
        else:
            self.console.print(
                f"[yellow]No new packages added to workspace '[cyan]{branch}[/cyan]' (may already exist)[/yellow]"
            )

        return 0

    def action_remove_package(self):
        """Remove a package from a workspace."""
        branch = self.args.branch
        package_name = self.args.package

        if not branch:
            logger.error("Branch name is required")
            return 1

        if not package_name:
            logger.error("Package name is required")
            return 1

        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        resolved_package = BuildUtils.get_package_name(package_name)

        if self.workspace_service.remove_package_from_workspace(branch, resolved_package):
            self.console.print(
                f"[green]✓ Removed package '[cyan]{resolved_package}[/cyan]' from workspace with branch '[cyan]{branch}[/cyan]'[/green]"
            )
        else:
            self.console.print(
                f"[yellow]Package '[cyan]{resolved_package}[/cyan]' was not in workspace '[cyan]{branch}[/cyan]'[/yellow]"
            )
        return 0

    def _select_reverse_dependencies(self, package_name: str, reverse_deps, dag) -> Optional[List[str]]:
        """
        Display reverse dependencies and let user select which ones to include.

        Args:
            package_name: The name of the source package
            reverse_deps: List of DAGNodes
            dag: The dependency DAG for calculating depths

        Returns:
            List of selected package names, or None if cancelled
        """
        if not reverse_deps:
            return []

        unique_deps = self._deduplicate_dependencies(reverse_deps, dag)
        self._display_dependencies_table(package_name, unique_deps)
        choices = self._create_choices(unique_deps)

        return self._handle_user_selection(package_name, reverse_deps, choices, dag)

    def _deduplicate_dependencies(self, reverse_deps, dag):
        """Remove duplicate dependencies and return sorted list with depths."""
        unique_packages = {}
        for node in reverse_deps:
            if node.package not in unique_packages:
                depth = dag.calculate_node_depth(node)
                unique_packages[node.package] = (node, depth)
        return sorted(unique_packages.values(), key=lambda x: x[0].package)

    def _display_dependencies_table(self, package_name: str, deps):
        """Display table of reverse dependencies."""
        self.console.print(f"\n[bold]Reverse dependencies found for package '[cyan]{package_name}[/cyan]':[/bold]")

        table = Table(
            title=f"Packages that depend on {package_name}",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Package Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Graph Depth", justify="center")

        for node, depth in deps:
            table.add_row(node.package, node.version or "N/A", str(depth))

        self.console.print(table)

    def _create_choices(self, deps):
        """Create choices list for prompt-toolkit."""
        choices = []
        for node, depth in deps:
            choice_text = node.package
            if node.version:
                choice_text += f" (v{node.version})"
            choice_text += f" [depth: {depth}]"
            choices.append((node.package, choice_text))
        return choices

    def _handle_user_selection(self, package_name: str, reverse_deps, choices, dag):
        """Handle user selection with prompt-toolkit."""
        self.console.print("\n[bold]Select packages to include in the workspace:[/bold]")
        self.console.print("[dim]Use arrow keys to navigate, space to select/deselect, enter to confirm[/dim]")

        try:
            selected_packages = checkboxlist_dialog(
                title="Select packages:",
                text="Select packages to include in the workspace:",
                values=choices,
            ).run()

            if selected_packages is None:
                self.console.print("[yellow]Selection cancelled.[/yellow]")
                return None

            if not selected_packages:
                self.console.print("[yellow]No packages selected.[/yellow]")
                return []

            self.console.print(f"\n[bold]Selected packages:[/bold] {', '.join(selected_packages)}")

            if Confirm.ask("Proceed with this selection?", default=True):
                return selected_packages
            return self._select_reverse_dependencies(package_name, reverse_deps, dag)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Selection cancelled.[/yellow]")
            return None

    def execute(self):
        action_name = self.args.action.replace("-", "_")
        action_method = getattr(self, f"action_{action_name}", None)
        if action_method and callable(action_method):
            return action_method()

        logger.error("Unknown action: %s", self.args.action)
        return 1
