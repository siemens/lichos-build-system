# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import subprocess
from typing import Optional

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

    @classmethod
    def add_arguments(cls, sp):
        subparsers = sp.add_subparsers(dest="action", help="workspace actions")

        create_parser = subparsers.add_parser("create", help="create a new workspace")
        create_parser.add_argument("package", nargs="?", help="package name for the workspace")
        create_parser.add_argument(
            "--rev-deps",
            action="store_true",
            help="include reverse dependencies (packages that depend on this package) - may take longer"
        )

        enter_parser = subparsers.add_parser("enter", help="enter a workspace")
        enter_parser.add_argument("workspace_name", nargs="?", help="name of workspace to enter (if not specified, you'll be prompted to choose)")
        enter_parser.add_argument("package", nargs="?", help="filter workspaces by package name")

        list_parser = subparsers.add_parser("list", help="list all workspaces")
        list_parser.add_argument("package", nargs="?", help="filter workspaces by package name")

        delete_parser = subparsers.add_parser("delete", help="delete a workspace")
        delete_parser.add_argument("package", nargs="?", help="filter workspaces by package name")

        subparsers.add_parser("show", help="show workspace details")

        check_parser = subparsers.add_parser("check", help="check dependency versions for workspace packages")
        check_parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Don't wait for pipeline completion; use latest available pipeline results",
        )

        add_package_parser = subparsers.add_parser("add-package", help="add a package to a workspace")
        add_package_parser.add_argument("package", help="package name to add")
        add_package_parser.add_argument(
            "--rev-deps",
            action="store_true",
            help="include reverse dependencies (packages that depend on this package) - may take longer"
        )

        remove_package_parser = subparsers.add_parser("remove-package", help="remove a package from a workspace")
        remove_package_parser.add_argument("package", help="package name to remove")

        graph_parser = subparsers.add_parser("graph", help="show dependency graph for workspace packages")
        graph_parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Don't wait for pipeline completion; use latest available pipeline results",
        )

        subparsers.add_parser("merge", help="merge all opened merge requests in the workspace")

        subparsers.add_parser("changes", help="show links to changes for each package in the workspace")

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

        package_names_to_add = [package_name]

        if self.args.rev_deps:
            all_packages = self.package_service.get_all_packages()

            logger.info("Building dependency DAG for reverse dependency analysis")
            dag = self.dependency_service.build_dependency_dag(
                all_packages, self.args.branch, wait_for_completion=False
            )

            reverse_deps = dag.get_reverse_deps(package.name)

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

        if self.args.workspace_name:
            branch_name = self.args.workspace_name
            os.environ["LICHOS_BRANCH"] = branch_name
            self.console.print(f"[green]Entering workspace '[cyan]{branch_name}[/cyan]'[/green]")
            r = subprocess.run([os.environ.get("SHELL", "/bin/sh")], check=False)
            return r.returncode
        
        workspaces = []
        package_name = BuildUtils.get_package_name(self.args.package)
        if package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(package_name)
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
        package_name = BuildUtils.get_package_name(self.args.package)
        if package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(package_name)
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
            self.console.print(f"\n[bold yellow]Warning:[/bold yellow] Deleting workspace '[cyan]{branch}[/cyan]' will delete the branch on ALL packages in this workspace:")
            if workspace.packages:
                for pkg in workspace.packages:
                    self.console.print(f"  [yellow]•[/yellow] {pkg.name}")
            else:
                self.console.print("  [dim](no packages found)[/dim]")
            if not Confirm.ask(
                f"\nAre you sure you want to delete workspace '[cyan]{branch}[/cyan]' and all its branches?",
                default=False,
            ):
                self.console.print("[yellow]Workspace deletion cancelled[/yellow]")
                return 0
            if self.workspace_service.delete_workspace(branch):
                self.console.print(f"[green]✓ Deleted workspace with branch '[cyan]{branch}[/cyan]'[/green]")
                return 0
        workspaces = []
        package_name = BuildUtils.get_package_name(self.args.package)
        if package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(package_name)
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

        self.console.print("\n[bold]Select workspaces to delete:[/bold]")
        self.console.print("[dim]Use arrow keys to navigate, space to select/deselect, enter to confirm[/dim]")
        try:
            selected_branches = checkboxlist_dialog(
                title="Choose workspaces to delete:",
                text="Select workspaces to delete:",
                values=choices,
            ).run()

            if not selected_branches:
                self.console.print("[yellow]No workspaces selected for deletion[/yellow]")
                return 0
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Workspace deletion cancelled[/yellow]")
            return 0

        # Show warning about all packages that will be affected
        self.console.print("\n[bold yellow]Warning:[/bold yellow] Deleting a workspace will delete the branch on ALL packages in that workspace.\n")
        workspace_map = {ws.name: ws for ws in workspaces}
        for selected_branch in selected_branches:
            ws = workspace_map.get(selected_branch)
            if ws and ws.packages:
                pkg_names = ", ".join(pkg.name for pkg in ws.packages)
                self.console.print(f"  [cyan]{selected_branch}[/cyan] → packages: [yellow]{pkg_names}[/yellow]")
            else:
                self.console.print(f"  [cyan]{selected_branch}[/cyan] [dim](no packages)[/dim]")

        # Show confirmation for all selected workspaces
        workspace_list = "', '".join(selected_branches)
        if not Confirm.ask(
            f"\nAre you sure you want to delete workspace(s) '[cyan]{workspace_list}[/cyan]' including all branches on all packages?",
            default=False,
        ):
            self.console.print("[yellow]Workspace deletion cancelled[/yellow]")
            return 0

        # Delete all selected workspaces
        deleted_count = 0
        failed_branches = []

        for branch in selected_branches:
            if self.workspace_service.delete_workspace(branch):
                self.console.print(f"[green]✓ Deleted workspace '[cyan]{branch}[/cyan]'[/green]")
                deleted_count += 1
            else:
                logger.error("Workspace with branch '%s' does not exist", branch)
                failed_branches.append(branch)

        if deleted_count > 0:
            self.console.print(f"[green]✓ Successfully deleted {deleted_count} workspace(s)[/green]")

        if failed_branches:
            self.console.print(f"[red]✗ Failed to delete workspace(s): {', '.join(failed_branches)}[/red]")
            return 1

        return 0

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
        self.console.print(f"[bold]Packages:[/bold] {package_count}\n")

        if workspace.packages:
            col_width = max(len(pkg.name) for pkg in workspace.packages) + 2
            self.console.print(f"  [bold]{'Package'.ljust(col_width)}  Pipeline[/bold]")
            self.console.print(f"  {'-' * col_width}  {'--------'}")
            for package in workspace.packages:
                latest_pipeline = package.pipelines.get_latest(branch)
                if latest_pipeline:
                    self.console.print(f"  [cyan]{package.name.ljust(col_width)}[/cyan]", end="  ")
                    print(latest_pipeline.web_url)
                else:
                    self.console.print(f"  [cyan]{package.name.ljust(col_width)}[/cyan]  [dim]No pipeline found[/dim]")
        else:
            self.console.print("[yellow]No packages in workspace[/yellow]")

        return 0

    def action_check(self):
        """Check dependency versions for workspace packages."""
        branch = self.args.branch
        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        if not workspace.packages:
            self.console.print(f"[yellow]No packages in workspace '[cyan]{branch}[/cyan]'[/yellow]")
            return 0

        self.console.print(f"[bold]Checking dependency versions for workspace '[cyan]{branch}[/cyan]'...[/bold]\n")

        wait_for_completion = not self.args.no_wait

        logger.info("Building DAG for %d packages", len(workspace.packages))

        dag = self.dependency_service.build_dependency_dag(workspace.packages, branch, wait_for_completion)

        if not dag.nodes:
            self.console.print("[yellow]No dependency relationships found.[/yellow]")
            return 0

        all_version_results = self.dependency_service.check_all_dependency_versions_from_dag(dag)

        if not all_version_results:
            self.console.print("[yellow]No dependency version data found.[/yellow]")
            return 0
        
        workspace_package_names = {pkg.name for pkg in workspace.packages}
        relevant_results = [
            result for result in all_version_results
            if result.dependent_package in workspace_package_names
        ]

        if relevant_results:
            self.dependency_service.display_dependency_version_verification(relevant_results, self.console)
            return 0
    
        self.console.print("[yellow]No dependency version data found for workspace packages.[/yellow]")

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

        packages_to_add = [resolved_package]

        if self.args.rev_deps:
            all_packages = self.package_service.get_all_packages()

            logger.info("Building dependency DAG for reverse dependency analysis")
            dag = self.dependency_service.build_dependency_dag(all_packages, self.args.branch, wait_for_completion=False)

            reverse_deps = dag.get_reverse_deps(package.name)

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

    def _select_reverse_dependencies(self, package_name: str, reverse_deps, dag) -> Optional[list[str]]:
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

    def action_merge(self):
        """Merge all opened merge requests for each project in the workspace."""

        workspace = self.workspace_service.get_workspace(self.args.branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", self.args.branch)
            return 1

        if not workspace.packages:
            self.console.print(f"[yellow]No packages in workspace '[cyan]{self.args.branch}[/cyan]'[/yellow]")
            return 0

        self.console.print(f"[bold]Merging opened merge requests for workspace '[cyan]{self.args.branch}[/cyan]'[/bold]\n")

        total_merged = 0
        total_found = 0
        failed_merges = []

        for package in workspace.packages:
            merge_requests = package.merge_requests.list(
                state="opened",
                branch_name=self.args.branch,
                get_all=True
            )

            if not merge_requests:
                self.console.print(
                    f"[dim]Package '[cyan]{package.name}[/cyan]': No open merge requests[/dim]"
                )
                continue

            total_found += len(merge_requests)

            for mr in merge_requests:
                self.console.print(
                    f"Package '[cyan]{package.name}[/cyan]': Merging MR !{mr.iid} - {mr.title}"
                )

                if mr.merge():
                    total_merged += 1
                    self.console.print(
                        f"[green]✓ Successfully merged MR !{mr.iid}[/green]"
                    )
                else:
                    failed_merges.append((package.name, mr.iid, mr.title))
                    self.console.print(
                        f"[red]✗ Failed to merge MR !{mr.iid}[/red]"
                    )

        self.console.print()
        self.console.print(f"[bold]Summary:[/bold]")
        self.console.print(f"  Total merge requests found: {total_found}")
        self.console.print(f"  Successfully merged: [green]{total_merged}[/green]")

        if failed_merges:
            self.console.print(f"  Failed to merge: [red]{len(failed_merges)}[/red]")
            self.console.print("\n[bold]Failed merge requests:[/bold]")
            for pkg_name, mr_iid, mr_title in failed_merges:
                self.console.print(f"  - {pkg_name}: !{mr_iid} - {mr_title}")

        return 0 if not failed_merges else 1

    def action_changes(self):
        """Print links to changes for each package in the workspace.

        For each package:
        - If there is an open merge request on the workspace branch, print its URL.
        - Otherwise print a compare URL showing what the branch adds over the default branch.
        """
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

        if not workspace.packages:
            self.console.print(f"[yellow]No packages in workspace '[cyan]{branch}[/cyan]'[/yellow]")
            return 0

        rows = []
        for package in workspace.packages:
            merge_requests = package.merge_requests.list(
                state="opened",
                branch_name=branch,
                get_all=True,
            )
            if merge_requests:
                for mr in merge_requests:
                    rows.append((package.name, mr.web_url))
            else:
                rows.append((package.name, package.compare_url(package.default_branch, branch)))


        self.console.print(f"\n[bold]Changes for workspace '[cyan]{branch}[/cyan]':[/bold]")
        if rows:
            col_width = max(len(name) for name, _ in rows) + 2
            self.console.print(f"  [bold]{'Package'.ljust(col_width)}  Link[/bold]")
            self.console.print(f"  {'-' * col_width}  {'----'}")
            for name, url in rows:
                self.console.print(f"  [cyan]{name.ljust(col_width)}[/cyan]", end="  ")
                print(url)
        return 0

    def action_graph(self):
        """Show dependency graph for workspace packages."""
        branch = self.args.branch
        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        if not workspace.packages:
            self.console.print(f"[yellow]No packages in workspace '[cyan]{branch}[/cyan]'[/yellow]")
            return 0

        logger.info("Building dependency graph for %d packages", len(workspace.packages))

        self.console.print(f"Building dependency graph for workspace '[cyan]{branch}[/cyan]':")

        wait_for_completion = not self.args.no_wait

        dag = self.dependency_service.build_dependency_dag(workspace.packages, branch, wait_for_completion)

        if not dag.nodes:
            self.console.print("[yellow]No dependency relationships found.[/yellow]")
            return 0

        if self.args.dump:
            from rich.json import JSON
            dag_data = dag.to_dict()
            self.console.print(JSON.from_data(dag_data))
            return 0

        self.console.print(
            f"\n[bold cyan]Dependency Analysis - {len(dag.nodes)} packages (workspace: {branch}):[/bold cyan]"
        )
        self.console.print("=" * 70)
        self.console.print(f"[cyan]Total packages:[/cyan] {len(dag.nodes)}")

        total_deps = sum(len(node.direct_dependencies) for node in dag.nodes.values())

        self.console.print(f"[cyan]Total dependency relationships:[/cyan] {total_deps}")

        self.console.print()
        self.dependency_service.print_dag_tree(dag, self.console)

        self.console.print("\n[bold green]Dependency Levels[/bold green]")
        self.console.print("-" * 20)

        levels = dag.calculate_build_levels()
        for level in sorted(levels.keys()):
            nodes = levels[level]
            level_color = "green" if level == 0 else "yellow" if level == 1 else "orange1" if level == 2 else "red"
            package_names = sorted([node.package for node in nodes])
            self.console.print(
                f"[bold {level_color}]Level {level}[/bold {level_color}] (depth {level}): {', '.join(package_names)}"
            )

        return 0

    def execute(self):
        action_name = self.args.action.replace("-", "_")
        action_method = getattr(self, f"action_{action_name}", None)
        if action_method and callable(action_method):
            return action_method()

        logger.error("Unknown action: %s", self.args.action)
        return 1
