import logging
import time

from rich import box
from rich.panel import Panel
from rich.table import Table

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProjectFetchingError, ValidationError
from lichoscli.core.models.dag import DAGNode, DAGNodeStatus, DependencyGraph
from lichoscli.core.services import (
    DependencyService,
    NotifyService,
    PackageService,
    StorageService,
    WorkspaceService,
)
from lichoscli.core.services.notify import NotificationData
from lichoscli.utils.git import GitUtils

logger = logging.getLogger(__name__)


class ScheduleCommand(Command):
    """Schedule sequential builds for all packages in a workspace"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.workspace_service = di_container.obtain_ref(WorkspaceService)
        self.dependency_service = di_container.obtain_ref(DependencyService)

        self.storage_service = di_container.obtain_ref(StorageService)
        self.notify_service = di_container.obtain_ref(NotifyService)
        self.previous_dag = self.storage_service.load_workspace_state(self.args.branch)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument(
            "--skip-version-check",
            action="store_true",
            help="Skip version check; build all packages",
        )
        sp.add_argument(
            "--poll-interval",
            type=int,
            default=10,
            help="Interval in seconds to check build status (default: 10)",
        )
        # TODO: remove this after deleting it from 00ci
        sp.add_argument(
            "--persist",
            action="store_true",
            help="Enable state persistence using storage service",
        )


    def execute(self) -> int:
        """Execute the schedule command"""
        workspace = self.workspace_service.get_workspace(self.args.branch)
        if not workspace:
            self.console.print(f"[bold red]Error:[/bold red] Workspace '{self.args.branch}' not found")
            return 1

        if not workspace.packages:
            self.console.print(f"No packages found in workspace '{self.args.branch}'")
            return 0

        self.console.print(f"Scheduling builds for workspace '[cyan]{self.args.branch}[/cyan]' packages:")

        current_dag: DependencyGraph = self.dependency_service.build_dependency_dag(
            workspace.packages, self.args.branch
        )
        if not current_dag:
            self.console.print("[red]Error:[/red] Could not build dependency DAG")
            return 1

        if self.previous_dag and not self.args.skip_version_check:
            if not self.dependency_service.has_dag_state_changed(self.previous_dag, current_dag):
                self.console.print("\n[yellow]Skipping rebuild - no changes to build graph state since last run[/yellow]")
                return 0

        if self.args.skip_version_check:
            self.console.print("[yellow]Warning:[/yellow] Skipping version checking - building all packages")
            self.console.print("\n[bold blue]Building dependency DAG for analysis...[/bold blue]")
            self.console.print(f"\n[bold cyan]Dependency Analysis - {len(current_dag.nodes)} packages:[/bold cyan]")
            self.dependency_service.print_dag_tree(current_dag, self.console)
            dependencies_by_build_level = current_dag.calculate_build_levels()
        else:
            dependencies_by_build_level = self._build_dependency_schedule(current_dag)

        try:
            if all(len(nodes) == 0 for nodes in dependencies_by_build_level.values()):
                self.console.print("[green]All packages are up to date![/green] No builds needed.")

                if self.notify_service:
                    self._send_build_notification(current_dag)

                self.storage_service.save_workspace_state(self.args.branch, current_dag)
                self.console.print("[green]✓[/green] Persisted current DAG state")

                return 0

            self._display_build_schedule(dependencies_by_build_level)

            if self.args.dry:
                self.console.print("\n[cyan]Dry run completed - no builds were triggered[/cyan]")
                if not self.args.skip_version_check and dependencies_by_build_level:
                    self.console.print(
                        "[bold yellow]With version checking enabled, only packages with dependency mismatches would be built[/bold yellow]"
                    )
                return 0

            return self._execute_build_schedule(dependencies_by_build_level, current_dag)

        except (ProjectFetchingError, ValidationError) as e:
            logger.error("Error in schedule command: %s", str(e))
            self.console.print(f"[bold red]Error:[/bold red] {str(e)}")
            return 1

    def _build_dependency_schedule(self, dag: DependencyGraph) -> dict[int, list[DAGNode]]:
        """
        Build a dependency-aware schedule that only includes packages needing rebuilds.

        Args:
            dag: The dependency graph containing all packages with their dependencies

        Returns:
            Dictionary mapping build levels to lists of DAG nodes that need rebuilding
        """
        self.console.print("\n[bold blue]Analyzing package dependencies and versions...[/bold blue]")

        if not dag or not dag.nodes:
            logger.warning("Invalid DAG provided, cannot proceed with scheduling")
            return {}

        self.console.print(f"\n[bold cyan]Dependency Analysis - {len(dag.nodes)} packages:[/bold cyan]")
        self.dependency_service.print_dag_tree(dag, self.console)

        packages_needing_rebuild = set()
        version_mismatch_details = []
        failed_pipeline_packages = []

        self.console.print("\n[bold blue]Checking for packages with failed pipelines...[/bold blue]")
        for package_name, node in dag.nodes.items():
            pipeline = node.project.pipelines.get_latest(self.args.branch, use_cache=False)
            if pipeline and pipeline.status.is_failed:
                packages_needing_rebuild.add(package_name)
                failed_pipeline_packages.append(package_name)

        if failed_pipeline_packages:
            self.console.print(
                f"[yellow]Found {len(failed_pipeline_packages)} packages with failed pipelines:[/yellow]"
            )

        all_version_check_results = self.dependency_service.check_all_dependency_versions_from_dag(
            dag
        )

        for result in all_version_check_results:
            if not result.is_correct:
                packages_needing_rebuild.add(result.dependent_package)
                version_mismatch_details.append(result)
                logger.info(
                    "Version mismatch: %s built with %s v%s, but %s v%s is now available",
                    result.dependent_package,
                    result.binary_package,
                    result.used_version,
                    result.source_package,
                    result.expected_version,
                )

        mismatch_results = [r for r in all_version_check_results if not r.is_correct]
        self.dependency_service.display_dependency_version_verification(mismatch_results, self.console)

        initial_rebuild_packages = packages_needing_rebuild.copy()
        for package_name in initial_rebuild_packages:
            transitive_dependents = dag.get_transitive_dependents(package_name)
            packages_needing_rebuild.update(node.package for node in transitive_dependents)

        for package_name, node in dag.nodes.items():
            if package_name not in packages_needing_rebuild:
                node.set_status(DAGNodeStatus.SUCCESS)

        if not packages_needing_rebuild:
            self.console.print(
                "\n[green]All packages have correct dependency versions and no failed pipelines![/green]"
            )
            return {}

        filtered_nodes = [dag.get_node(pkg_name) for pkg_name in packages_needing_rebuild if dag.get_node(pkg_name)]
        build_levels_by_nodes = dag.calculate_build_levels(filtered_nodes)

        total_packages = len([node.project for node in dag.nodes.values() if node.project])
        self.console.print(
            f"\n[cyan]Packages needing rebuild:[/cyan] {len(packages_needing_rebuild)} of {total_packages})"
        )

        return build_levels_by_nodes

    def _display_build_schedule(self, dependencies_by_build_level: dict[int, list[DAGNode]]) -> None:
        """Display the planned build schedule"""
        self.console.print(Panel.fit("Build Schedule", style="bold blue"))

        table = Table(box=box.ROUNDED)
        table.add_column("Level", style="bold cyan", justify="center")
        table.add_column("Count", style="bold yellow", justify="center")
        table.add_column("Packages", style="white")
        table.add_column("Reason", style="dim")

        total_packages = sum(len(nodes) for nodes in dependencies_by_build_level.values())

        for level in sorted(dependencies_by_build_level.keys()):
            nodes = dependencies_by_build_level[level]
            package_names = ", ".join([node.project.name for node in nodes if node.project])

            if level == 0:
                reason = "Dependencies ready"
            else:
                reason = f"Depends on level {level-1}"

            table.add_row(str(level), str(len(nodes)), package_names, reason)

        self.console.print(table)
        self.console.print(f"\n[bold]Total packages to build:[/bold] {total_packages}")
        self.console.print()

    def _execute_build_schedule(
        self, dependencies_by_build_level: dict[int, list[DAGNode]], dag: DependencyGraph
    ) -> int:
        """Execute the build schedule level by level with sequential waiting"""
        # Reset all scheduled packages to PENDING before starting builds
        for level_nodes in dependencies_by_build_level.values():
            for node in level_nodes:
                node.set_status(DAGNodeStatus.PENDING)

        total_builds = 0
        failed_builds = 0

        for level in sorted(dependencies_by_build_level.keys()):
            nodes = dependencies_by_build_level[level]
            self.console.print(f"\n[bold]Executing Level {level} builds ({len(nodes)} packages)...[/bold]")

            triggered_packages = []
            for node in nodes:
                pkg = node.project
                self.console.print(
                    f"  Triggering build for [cyan]{pkg.name}[/cyan] on branch [cyan]{self.args.branch}[/cyan]..."
                )
                pipeline = pkg.pipelines.trigger_build(self.args.branch)

                if pipeline:
                    self.console.print(f"  [green]✓[/green] Successfully triggered build for [cyan]{pkg.name}[/cyan]")
                    print("    Pipeline: " + pipeline.web_url)
                    triggered_packages.append(pkg)
                    total_builds += 1
                    node.set_status(DAGNodeStatus.BUILDING)
                else:
                    self.console.print(f"  [red]✗[/red] Failed to trigger build for [cyan]{pkg.name}[/cyan]")
                    failed_builds += 1
                    node.set_status(DAGNodeStatus.FAILED)

            if not triggered_packages:
                self.console.print(f"Level {level} completed (no builds triggered)\n")
                continue

            building_nodes = dag.get_nodes_by_status(DAGNodeStatus.BUILDING)
            self.console.print(f"\nWaiting for {len(building_nodes)} builds to complete...")
            success = self._wait_for_builds_completion(building_nodes)

            if not success:
                logger.error("Some builds failed at level %d. Stopping schedule.", level)
                self.console.print(f"[bold red]Build schedule stopped at level {level} due to failures[/bold red]")

                if dag:
                    if self.notify_service:
                        self._send_build_notification(dag)
                    self.storage_service.save_workspace_state(self.args.branch, dag)
                return 0

            self.console.print(f"[green]All builds completed successfully for level {level}[/green]")
            self.console.print(f"Level {level} completed\n")

        self.console.print("[bold]Build scheduling completed:[/bold]")
        self.console.print(f"  [green]Successfully triggered:[/green] {total_builds}")
        self.console.print(f"  [red]Failed:[/red] {failed_builds}")

        if self.notify_service:
            self._send_build_notification(dag)

        self.storage_service.save_workspace_state(self.args.branch, dag)

        return 0

    def _wait_for_builds_completion(self, building_nodes: list[DAGNode]) -> bool:
        """Wait for all builds in the given building nodes to complete successfully."""

        current_building_nodes = [node for node in building_nodes if node.status == DAGNodeStatus.BUILDING]
        previous_count = len(current_building_nodes)

        package_names = [node.package for node in current_building_nodes]
        if len(package_names) <= 3:
            packages_text = ", ".join(package_names)
        else:
            packages_text = f"{', '.join(package_names[:3])}... ({len(package_names)} total)"

        self.console.print(
            f"[bold blue]Monitoring builds:[/bold blue] Waiting for {len(current_building_nodes)} packages: {packages_text}"
        )
        has_failures = False

        while current_building_nodes:
            for node in current_building_nodes:
                pkg = node.project
                if not pkg:
                    continue

                pipeline = pkg.pipelines.get_latest(self.args.branch, use_cache=False)
                if not pipeline:
                    continue
                if pipeline.status.is_successful:
                    self.console.print(f"  [green]✓[/green] [cyan]{node.package}[/cyan] completed successfully")
                    print("    Pipeline: " + pipeline.web_url)
                    node.set_status(DAGNodeStatus.SUCCESS)
                elif pipeline.status.is_failed:
                    self.console.print(
                        f"  [red]✗[/red] [cyan]{node.package}[/cyan] failed with status: {pipeline.status.to_display_string()}"
                    )
                    print("    Pipeline: " + pipeline.web_url)
                    node.set_status(DAGNodeStatus.FAILED)
                    has_failures = True
                elif pipeline.status.is_active or pipeline.status.is_waiting:
                    pass
                else:
                    self.console.print(
                        f"[yellow]W[/yellow] Unexpected pipeline status for [cyan]{node.package}[/cyan]: {pipeline.status.to_display_string()}"
                    )

            time.sleep(self.args.poll_interval)
            current_building_nodes = [node for node in building_nodes if node.status == DAGNodeStatus.BUILDING]

            current_count = len(current_building_nodes)
            if current_count != previous_count and current_count > 0:
                package_names = [node.package for node in current_building_nodes]
                if len(package_names) <= 3:
                    packages_text = ", ".join(package_names)
                else:
                    packages_text = f"{', '.join(package_names[:3])}... ({len(package_names)} total)"

                self.console.print(f"[dim]Still waiting for {current_count} packages: {packages_text}[/dim]")
                previous_count = current_count

        if has_failures:
            failed_nodes = [node for node in building_nodes if node.status == DAGNodeStatus.FAILED]
            failed_package_names = [node.package for node in failed_nodes]
            self.console.print(f"[bold red]Builds failed for:[/bold red] {', '.join(failed_package_names)}")
            return False

        self.console.print("[bold blue]All builds completed successfully[/bold blue]")
        return True

    def _generate_failing_package_commit_urls(self, failed_nodes: list[DAGNode]) -> dict[str, str]:
        """
        Generate commit URLs for failing packages when no previous DAG is available.

        Args:
            failed_nodes: List of failed DAG nodes

        Returns:
            Dict mapping package names to their commit URLs
        """
        commit_urls = {}

        for node in failed_nodes:
            if node.project and node.commit_sha:
                try:
                    project_path = node.project.path_with_namespace
                    project_id = str(node.project.id) if hasattr(node.project, "id") else None

                    host = self.args.host
                    if not host.startswith("https://"):
                        host = f"https://{host}"
                    commit_url = f"{host}/{project_path}/-/commit/{node.commit_sha}"
                    if project_id:
                        commit_url += f"?from_project_id={project_id}"

                    commit_urls[node.package] = commit_url
                except AttributeError:
                    continue

        return commit_urls

    def _send_build_notification(self, dag: DependencyGraph) -> None:
        """Send notification about build results and generate comparison URLs for failed packages."""
        pipeline_urls = {}

        for package_name, node in dag.nodes.items():
            if node.project:
                pipeline = node.project.pipelines.get_latest(self.args.branch, use_cache=False)
                pipeline_urls[package_name] = pipeline.web_url if pipeline else "N/A"

        failed_nodes = dag.get_nodes_by_status(DAGNodeStatus.FAILED)
        successful_nodes = dag.get_nodes_by_status(DAGNodeStatus.SUCCESS)

        package_comparison_urls = {}

        # Only generate comparison URLs if there are failed packages
        if failed_nodes:
            if self.previous_dag:

                changed_packages = self.dependency_service.get_dag_changed_packages(self.previous_dag, dag)

                if changed_packages:
                    self.console.print(
                        f"[dim]Generating comparison URLs for {len(changed_packages)} changed packages...[/dim]"
                    )
                    package_comparison_urls = GitUtils.generate_package_comparison_urls_from_projects(
                        changed_packages, self.args.host
                    )
                    self.console.print(f"[dim]Generated {len(package_comparison_urls)} comparison URLs[/dim]")
            else:
                self.console.print(f"[dim]Generating commit URLs for {len(failed_nodes)} failing packages...[/dim]")
                package_comparison_urls = self._generate_failing_package_commit_urls(failed_nodes)
                self.console.print(f"[dim]Generated {len(package_comparison_urls)} commit URLs[/dim]")

        self.console.print("\n[yellow]Sending build status notification...[/yellow]")
        failed_packages = [node.package for node in failed_nodes]
        successful_packages = [node.package for node in successful_nodes]
        notification_data = NotificationData(
            failed_packages=failed_packages,
            successful_packages=successful_packages,
            dag_nodes=dag.nodes,
            pipeline_urls=pipeline_urls,
            package_comparison_urls=package_comparison_urls,
        )

        success = self.notify_service.send_workspace_notification(self.args.branch, notification_data)
        if success:
            self.console.print("[green]✓[/green] Build status notification sent successfully")
            if package_comparison_urls:
                if self.previous_dag:
                    self.console.print(
                        f"[green]✓[/green] Included {len(package_comparison_urls)} package comparison URLs"
                    )
                else:
                    self.console.print(
                        f"[green]✓[/green] Included {len(package_comparison_urls)} failing package commit URLs"
                    )
        else:
            self.console.print("[red]✗[/red] Failed to send build status notification")
