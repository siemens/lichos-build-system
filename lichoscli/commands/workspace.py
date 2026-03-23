# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import subprocess
from typing import Optional

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models.dag import DAGNodeStatus
from lichoscli.core.services import DependencyService, PackageService, WorkspaceService
from lichoscli.ui import Cell, Choice, Table
from lichoscli.ui.presenters.dag import dag_to_tree, version_check_summary
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

        add_package_parser = subparsers.add_parser("add", help="add a package to a workspace")
        add_package_parser.add_argument("package", help="package name to add")
        add_package_parser.add_argument(
            "--rev-deps",
            action="store_true",
            help="include reverse dependencies (packages that depend on this package) - may take longer"
        )

        remove_package_parser = subparsers.add_parser("remove", help="remove a package from a workspace")
        remove_package_parser.add_argument("package", nargs="?", help="package name to remove (if not specified, you'll be prompted to choose)")

        graph_parser = subparsers.add_parser("graph", help="show dependency graph for workspace packages")
        graph_parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Don't wait for pipeline completion; use latest available pipeline results",
        )

        subparsers.add_parser("merge", help="merge all opened merge requests in the workspace")

        subparsers.add_parser("changes", help="show links to changes for each package in the workspace")

    @staticmethod
    def _workspace_choice_label(workspace) -> str:
        if getattr(workspace, "packages", None):
            package_names = [pkg.name for pkg in workspace.packages]
            return f"{workspace.name} [{', '.join(package_names)}]"
        return workspace.name

    def _select_workspace_to_enter(self, workspaces) -> str | None:
        return self.prompts.select_one(
            title="Choose workspace",
            text="Select a workspace to enter:",
            choices=[Choice(value=workspace.name, label=self._workspace_choice_label(workspace)) for workspace in workspaces],
        )

    def _confirm_workspace_delete(self, branch: str, packages) -> bool:
        package_names = [pkg.name for pkg in packages] if packages else []
        self.output.warning(
            f"Deleting workspace '{branch}' will remove the branch on all packages in that workspace.",
        )
        if package_names:
            self.output.print("\n".join(f"  - {package_name}" for package_name in package_names))
        else:
            self.output.muted("  (no packages found)")

        return self.prompts.confirm(
            f"Are you sure you want to delete workspace '{branch}' and all its branches?",
            default=False,
        )

    def _select_workspaces_to_delete(self, workspaces) -> list[str] | None:
        return self.prompts.select_many(
            title="Choose workspaces to delete",
            text="Select workspaces to delete:",
            choices=[Choice(value=workspace.name, label=self._workspace_choice_label(workspace)) for workspace in workspaces],
        )

    def _confirm_multiple_workspace_delete(self, selected_branches: list[str], workspace_map) -> bool:
        self.output.warning(
            "Deleting a workspace will remove the branch on all packages in that workspace.",
        )
        for branch in selected_branches:
            workspace = workspace_map.get(branch)
            if workspace and workspace.packages:
                package_names = ", ".join(pkg.name for pkg in workspace.packages)
                self.output.print(f"  {branch}: {package_names}")
            else:
                self.output.muted(f"  {branch}: (no packages)")

        return self.prompts.confirm(
            f"Are you sure you want to delete workspace(s) '{', '.join(selected_branches)}' including all branches on all packages?",
            default=False,
        )

    def _select_packages_to_remove(self, packages) -> list[str] | None:
        return self.prompts.select_many(
            title="Choose packages to remove",
            text="Select packages to remove from the workspace:",
            choices=[Choice(value=pkg.name, label=pkg.name) for pkg in packages],
        )

    def _select_reverse_dependencies_from_options(self, package_name: str, deps) -> list[str] | None:
        rev_dep_table = Table(title="Reverse dependencies for {0}".format(package_name))
        rev_dep_table.add_column("Package Name", style="accent")
        rev_dep_table.add_column("Version", style="success")
        rev_dep_table.add_column("Graph Depth", justify="center")
        for node, depth in deps:
            rev_dep_table.add_row(node.package, node.version or "N/A", str(depth))
        self.output.table(rev_dep_table)

        choices = []
        for node, depth in deps:
            label = node.package
            if node.version:
                label += f" (v{node.version})"
            label += f" [depth: {depth}]"
            choices.append(Choice(value=node.package, label=label))

        while True:
            selected_packages = self.prompts.select_many(
                title="Select packages",
                text="Select packages to include in the workspace:",
                choices=choices,
            )

            if selected_packages is None:
                self.output.warning("Selection cancelled.")
                return None

            if not selected_packages:
                self.output.warning("No packages selected.")
                return []

            self.output.print(f"Selected packages: {', '.join(selected_packages)}")
            if self.prompts.confirm("Proceed with this selection?", default=True):
                return selected_packages

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

            reverse_deps = dag.get_transitive_dependents(package.name)

            if not reverse_deps:
                self.output.warning(
                    f"No reverse dependencies found for package '{package_name}'",
                )
            else:
                selected_deps = self._select_reverse_dependencies(package_name, reverse_deps, dag)
                if selected_deps is None:
                    self.output.warning("Workspace creation cancelled")
                    return 0

                package_names_to_add.extend(selected_deps)

        try:
            workspace = self.workspace_service.create_workspace(self.args.branch, package_names_to_add)
            self.output.success(
                f"Created workspace for branch '{self.args.branch}'\n"
                f"Added packages: {', '.join(pkg.name for pkg in workspace.packages)}",
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
            self.output.success(f"Entering workspace '{branch_name}'")
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

        branch_name = self._select_workspace_to_enter(workspaces)
        if branch_name is None:
            self.output.warning("Workspace selection cancelled")
            return 0

        os.environ["LICHOS_BRANCH"] = branch_name
        self.output.success(f"Entering workspace '{branch_name}'")

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
            self.output.warning("No workspaces found")
            return 0

        current_workspace = self.workspace_service.get_current_workspace()
        current_name = current_workspace.name if current_workspace else None

        ws_table = Table(title="Available Workspaces")
        ws_table.add_column("Workspace", no_wrap=True)
        ws_table.add_column("Packages")
        ws_table.add_column("Current", no_wrap=True)
        for workspace in workspaces:
            package_names = ", ".join(pkg.name for pkg in workspace.packages) if workspace.packages else "-"
            current_cell = Cell("current", style="success") if workspace.name == current_name else ""
            ws_table.add_row(workspace.name, package_names, current_cell)
        self.output.table(ws_table)

        return 0

    def action_delete(self):
        """Delete a workspace."""
        branch = self.args.branch

        if self.args.branch and self.args.branch_explicitly_provided:
            workspace = self.workspace_service.get_workspace(branch)
            if not workspace:
                logger.error("Workspace with branch '%s' does not exist", branch)
                return 1
            if not self._confirm_workspace_delete(branch, workspace.packages):
                self.output.warning("Workspace deletion cancelled")
                return 0
            if self.workspace_service.delete_workspace(branch):
                self.output.success(f"Deleted workspace '{branch}'")
                return 0
        workspaces = []
        package_name = BuildUtils.get_package_name(self.args.package)
        if package_name:
            workspaces = self.workspace_service.get_workspaces_by_package(package_name)
        else:
            workspaces = self.workspace_service.list_workspaces()

        if not workspaces:
            self.output.warning("No workspaces found")
            return 0

        selected_branches = self._select_workspaces_to_delete(workspaces)
        if selected_branches is None:
            self.output.warning("Workspace deletion cancelled")
            return 0
        if not selected_branches:
            self.output.warning("No workspaces selected for deletion")
            return 0

        workspace_map = {ws.name: ws for ws in workspaces}
        if not self._confirm_multiple_workspace_delete(selected_branches, workspace_map):
            self.output.warning("Workspace deletion cancelled")
            return 0

        deleted_count = 0
        failed_branches = []

        for branch in selected_branches:
            if self.workspace_service.delete_workspace(branch):
                self.output.success(f"Deleted workspace '{branch}'")
                deleted_count += 1
            else:
                logger.error("Workspace with branch '%s' does not exist", branch)
                failed_branches.append(branch)

        if deleted_count > 0:
            self.output.success(f"Successfully deleted {deleted_count} workspace(s)")
        if failed_branches:
            self.output.error(
                f"Failed to delete workspace(s): {', '.join(failed_branches)}",
            )
        if failed_branches:
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

        package_rows = []
        if workspace.packages:
            for package in workspace.packages:
                latest_pipeline = package.pipelines.get_latest(branch)
                package_rows.append((package.name, latest_pipeline.web_url if latest_pipeline else None))

        self.output.accent(f"Workspace: {workspace.name}")
        self.output.print(f"Packages: {len(package_rows)}")

        if not package_rows:
            self.output.warning("No packages in workspace")
            return 0

        show_table = Table()
        show_table.add_column("Package", no_wrap=True)
        show_table.add_column("Pipeline")
        for package_name, pipeline_url in package_rows:
            if pipeline_url:
                show_table.add_row(package_name, pipeline_url)
            else:
                show_table.add_row(package_name, Cell("No pipeline found", style="muted"))
        self.output.table(show_table)

        return 0

    def action_check(self):
        """Check dependency versions for workspace packages."""
        branch = self.args.branch
        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        if not workspace.packages:
            self.output.warning(f"No packages in workspace '{branch}'")
            return 0

        self.output.accent(f"Checking dependency versions for workspace '{branch}'")

        wait_for_completion = not self.args.no_wait

        logger.info("Building DAG for %d packages", len(workspace.packages))

        dag = self.dependency_service.build_dependency_dag(workspace.packages, branch, wait_for_completion)

        if not dag.nodes:
            self.output.warning("No dependency relationships found.")
            return 0

        all_version_results = self.dependency_service.check_all_dependency_versions_from_dag(dag)

        if not all_version_results:
            self.output.warning("No dependency version data found.")
            return 0

        workspace_package_names = {pkg.name for pkg in workspace.packages}
        relevant_results = [
            result for result in all_version_results
            if result.dependent_package in workspace_package_names
        ]

        if relevant_results:
            msg, style = version_check_summary(relevant_results)
            getattr(self.output, style)(msg)
            return 0

        self.output.warning("No dependency version data found for workspace packages.")

        return 0

    def action_add(self):
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

            reverse_deps = dag.get_transitive_dependents(package.name)

            if reverse_deps:
                selected_deps = self._select_reverse_dependencies(resolved_package, reverse_deps, dag)

                if selected_deps is None:
                    self.output.warning("Package addition cancelled")
                    return 0

                packages_to_add.extend(selected_deps)
            else:
                self.output.warning(
                    f"No reverse dependencies found for package '{resolved_package}'",
                )

        added_packages = []
        for pkg_name in packages_to_add:
            if self.workspace_service.add_package_to_workspace(branch, pkg_name):
                added_packages.append(pkg_name)

        if added_packages:
            self.output.success(
                f"Added packages to workspace '{branch}': {', '.join(added_packages)}",
            )
        else:
            self.output.warning(
                f"No new packages added to workspace '{branch}' (they may already exist)",
            )

        return 0

    def action_remove(self):
        """Remove a package from a workspace."""
        branch = self.args.branch
        package_name = self.args.package

        if not branch:
            logger.error("Branch name is required")
            return 1

        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        if not package_name:
            if not workspace.packages:
                self.output.warning(f"No packages in workspace '{branch}'")
                return 1
            selected_packages = self._select_packages_to_remove(workspace.packages)
            if selected_packages is None:
                self.output.warning("Package removal cancelled")
                return 0
            if not selected_packages:
                self.output.warning("Package removal cancelled")
                return 0
            for pkg_name in selected_packages:
                resolved = BuildUtils.get_package_name(pkg_name)
                if self.workspace_service.remove_package_from_workspace(branch, resolved):
                    self.output.success(
                        f"Removed package '{resolved}' from workspace '{branch}'",
                    )
                else:
                    self.output.warning(
                        f"Package '{resolved}' was not in workspace '{branch}'",
                    )
            return 0

        resolved_package = BuildUtils.get_package_name(package_name)

        if self.workspace_service.remove_package_from_workspace(branch, resolved_package):
            self.output.success(
                f"Removed package '{resolved_package}' from workspace '{branch}'",
            )
        else:
            self.output.warning(
                f"Package '{resolved_package}' was not in workspace '{branch}'",
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
        return self._select_reverse_dependencies_from_options(package_name, unique_deps)

    def _deduplicate_dependencies(self, reverse_deps, dag):
        """Remove duplicate dependencies and return sorted list with depths."""
        unique_packages = {}
        for node in reverse_deps:
            if node.package not in unique_packages:
                depth = dag.get_depth(node.package)
                unique_packages[node.package] = (node, depth)
        return sorted(unique_packages.values(), key=lambda x: x[0].package)

    def action_merge(self):
        """Merge all opened merge requests for each project in the workspace."""

        workspace = self.workspace_service.get_workspace(self.args.branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", self.args.branch)
            return 1

        if not workspace.packages:
            self.output.warning(f"No packages in workspace '{self.args.branch}'")
            return 0

        self.output.accent(
            f"Merging opened merge requests for workspace '{self.args.branch}'",
        )

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
                self.output.muted(f"Package '{package.name}': no open merge requests")
                continue

            total_found += len(merge_requests)

            for mr in merge_requests:
                self.output.print(f"Package '{package.name}': merging MR !{mr.iid} - {mr.title}")

                if mr.merge():
                    total_merged += 1
                    self.output.success(f"Successfully merged MR !{mr.iid}")
                else:
                    failed_merges.append((package.name, mr.iid, mr.title))
                    self.output.error(f"Failed to merge MR !{mr.iid}")

        self.output.accent("Summary")
        self.output.print(f"Total merge requests found: {total_found}")
        self.output.success(f"Successfully merged: {total_merged}")

        if failed_merges:
            self.output.error(f"Failed to merge: {len(failed_merges)}")
            for package_name, mr_iid, title in failed_merges:
                self.output.error(f"  - {package_name}: !{mr_iid} - {title}")

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
            self.output.warning(f"No packages in workspace '{branch}'")
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

        self.output.accent(f"Changes for workspace '{branch}'")
        for package_name, url in rows:
            self.output.print(f"  {package_name}")
            self.output.print(f"    {url}")
        return 0

    def action_graph(self):
        """Show dependency graph for workspace packages."""
        branch = self.args.branch
        workspace = self.workspace_service.get_workspace(branch)
        if not workspace:
            logger.error("Workspace with branch '%s' does not exist", branch)
            return 1

        if not workspace.packages:
            self.output.warning(f"No packages in workspace '{branch}'")
            return 0

        logger.info("Building dependency graph for %d packages", len(workspace.packages))

        self.output.accent(
            f"Analyzing package dependencies and versions for workspace '{branch}'",
        )

        wait_for_completion = not self.args.no_wait

        dag = self.dependency_service.build_dependency_dag(workspace.packages, branch, wait_for_completion)

        if not dag.nodes:
            self.output.warning("No dependency relationships found.")
            return 0

        version_results = self.dependency_service.check_all_dependency_versions_from_dag(dag)
        dag.apply_version_check_results(version_results)

        if self.args.dump:
            self.output.json(dag.to_dict())
            return 0

        total_deps = sum(len(node.direct_dependencies) for node in dag.nodes.values())

        self.output.accent(
            f"Dependency Analysis - {len(dag.nodes)} packages (workspace: {branch})",
        )
        self.output.print("Total packages: {0}\nTotal dependency relationships: {1}".format(len(dag.nodes), total_deps))
        self.output.print()
        self.output.tree(dag_to_tree(dag))

        return 0

    def execute(self):
        action_name = self.args.action.replace("-", "_")
        action_method = getattr(self, f"action_{action_name}", None)
        if action_method and callable(action_method):
            return action_method()

        logger.error("Unknown action: %s", self.args.action)
        return 1
