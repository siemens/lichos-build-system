"""Command to list build dependencies of a package."""

import logging
from typing import List, Optional


from lichoscli.commands.base import Command
from lichoscli.core.models import BuildDependency, Project
from lichoscli.core.services import DependencyService, PackageService

logger = logging.getLogger(__name__)


class BuildInfoCommand(Command):
    """List build dependencies of a package."""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.dependency_service = di_container.obtain_ref(DependencyService)

    @classmethod
    def add_arguments(cls, sp):
        """Add command arguments."""
        sp.add_argument(
            "package",
            nargs="?",
            help="Package name to show dependencies for (optional when using --rev-deps for all packages)",
        )
        sp.add_argument("--filter-arch", help="Filter dependencies by architecture")
        sp.add_argument(
            "--rev-deps",
            action="store_true",
            help="Show reverse dependencies (for specific package if provided, or DAG for all packages if not)",
        )
        sp.add_argument(
            "--check-versions",
            action="store_true",
            help="Check and display dependency version verification for reverse dependencies",
        )
        sp.add_argument(
            "--no-wait",
            action="store_true",
            help="Don't wait for pipeline completion; use latest available pipeline results",
        )

    def validate_args(self) -> None:
        """Validate command-specific arguments."""
        if not self.args.package and not self.args.rev_deps:
            raise ValueError("Package name is required when not using --rev-deps for all packages.")

        if self.args.check_versions and not self.args.package and not self.args.rev_deps:
            raise ValueError(
                "Package name is required when using --check-versions (unless using --rev-deps for all packages)."
            )

    def execute(self) -> int:
        """Execute the dependencies command."""

        if self.args.rev_deps:
            if self.args.package:
                package: Project = self.package_service.get_package(self.args.package)
                if not package:
                    print(f"Package '{self.args.package}' not found.")
                    return 1
                return self._handle_package_rev_deps(package)
            return self._handle_all_packages_rev_deps()

        if not self.args.package:
            print("Package name is required when not using --rev-deps.")
            return 1

        package: Project = self.package_service.get_package(self.args.package)
        if not package:
            print(f"Package '{self.args.package}' not found.")
            return 1

        return self._handle_dependencies(package)

    def _handle_dependencies(self, package: Project) -> int:
        """Handle regular forward dependencies."""

        wait_for_completion = not self.args.no_wait

        dependencies = self.dependency_service.get_forward_dependencies(package, self.args.branch, wait_for_completion)

        if not dependencies:
            print(f"No build dependencies found for package '{package.name}'")
            return 0

        output = self._format_forward_dependencies(package.name, dependencies, self.args.filter_arch)
        print(output)
        return 0

    def _format_forward_dependencies(
        self,
        package_name: str,
        dependencies: List[BuildDependency],
        filter_arch: Optional[str] = None,
    ) -> str:
        """Format forward dependencies for display."""
        if not dependencies:
            return f"No build dependencies found for package '{package_name}'"

        lines = [
            f"\nBuild Dependencies for '{package_name}':",
            "=" * (len(package_name) + 25),
        ]

        filtered_deps = dependencies
        if filter_arch:
            filtered_deps = [dep for dep in dependencies if dep.architecture == filter_arch]
            if not filtered_deps:
                return f"No dependencies found for architecture '{filter_arch}'"

        deps_by_arch = {}
        for dep in filtered_deps:
            arch = dep.architecture or "all"
            if arch not in deps_by_arch:
                deps_by_arch[arch] = []
            deps_by_arch[arch].append(dep)

        for arch in sorted(deps_by_arch.keys()):
            arch_deps = deps_by_arch[arch]
            lines.extend([f"\nArchitecture: {arch} ({len(arch_deps)} packages)", "-" * 40])

            for dep in sorted(arch_deps, key=lambda x: x.package):
                dep_info = f"  • {dep.package}"
                if dep.version:
                    dep_info += f" (= {dep.version})"
                lines.append(dep_info)

        lines.extend(
            [
                f"\nTotal build dependencies: {len(filtered_deps)}",
            ]
        )

        if len(deps_by_arch) > 1:
            lines.append(f"Architectures: {', '.join(sorted(deps_by_arch.keys()))}")

        lines.append("=" * 50)

        return "\n".join(lines)

    def _handle_package_rev_deps(self, package: Project) -> int:
        """Handle reverse dependency operations for a specific package."""
        wait_for_completion = not self.args.no_wait

        logger.info(
            "Building dependency DAG and getting reverse dependencies for package: %s",
            package.name,
        )

        all_projects: List[Project] = self.package_service.get_packages_by_branch(self.args.branch)
        if not all_projects:
            self.console.print("[red]No projects found in the group.[/red]")
            return 1

        logger.info("Building DAG for %d packages", len(all_projects))

        self.console.print(f"Building dependency DAG for branch '[cyan]{self.args.branch}[/cyan]':")

        dag = self.dependency_service.build_dependency_dag(all_projects, self.args.branch, wait_for_completion)

        if not dag.nodes:
            self.console.print("[yellow]No dependency relationships found.[/yellow]")
            return 0

        if package.name not in dag.nodes:
            self.console.print(f"[yellow]Package '{package.name}' not found in dependency graph.[/yellow]")
            return 0

        direct_dependents = dag.nodes[package.name].reverse_dependencies
        transitive_dependents = dag.get_transitive_dependents(package.name)

        self.console.print(
            f"\n[bold cyan]Reverse Dependencies for '{package.name}' (branch: {self.args.branch}):[/bold cyan]"
        )
        self.console.print("=" * 70)

        if not direct_dependents:
            self.console.print(f"[yellow]No packages depend on '{package.name}'.[/yellow]")
            return 0

        self.console.print(f"\n[bold green]Direct Dependencies ({len(direct_dependents)} packages):[/bold green]")
        for dep_name in sorted(direct_dependents):
            self.console.print(f"  • [cyan]{dep_name}[/cyan]")

        if len(transitive_dependents) > len(direct_dependents):
            self.console.print(
                f"\n[bold yellow]All Dependencies (transitive, {len(transitive_dependents)} packages):[/bold yellow]"
            )

            levels = dag.calculate_build_levels(transitive_dependents)

            for level_index, level in enumerate(sorted(levels.keys())):
                level_nodes = levels[level]
                level_color = (
                    "green" if level == 0 else ("yellow" if level == 1 else "orange1" if level == 2 else "red")
                )
                self.console.print(f"  [bold {level_color}]Level {level_index}:[/bold {level_color}]")
                for node in sorted(level_nodes, key=lambda n: n.package):
                    self.console.print(f"    • [cyan]{node.package}[/cyan]")

        # If --check-versions is specified, check versions using DAG
        if self.args.check_versions:
            self.console.print(
                f"\n[bold blue]Checking dependency versions for packages that depend on '{package.name}'...[/bold blue]"
            )

            all_version_results = self.dependency_service.check_all_dependency_versions_from_dag(
                dag, self.args.branch, wait_for_completion
            )

            relevant_results = []
            target_buildinfo = None

            if package.name in dag.nodes:
                target_buildinfo = dag.nodes[package.name].buildinfo

            if target_buildinfo and target_buildinfo.binary:
                target_binaries = set(target_buildinfo.binary)
                for result in all_version_results:
                    if result.binary_package in target_binaries:
                        relevant_results.append(result)

            if relevant_results:
                self.dependency_service.display_dependency_version_verification(relevant_results, self.console)
            else:
                self.console.print(
                    f"[yellow]No dependency version data found for packages depending on '{package.name}'.[/yellow]"
                )

        return 0

    def _handle_all_packages_rev_deps(self) -> int:
        """Handle reverse dependency operations for all packages (DAG)."""
        logger.info("Building reverse dependency graph for all packages")

        all_projects: List[Project] = self.package_service.get_packages_by_branch(self.args.branch)
        if not all_projects:
            self.console.print("[red]No projects found in the group.[/red]")
            return 1

        logger.info("Building DAG for %d packages", len(all_projects))

        self.console.print(f"Building dependency DAG for branch '[cyan]{self.args.branch}[/cyan]':")

        wait_for_completion = not self.args.no_wait

        dag = self.dependency_service.build_dependency_dag(all_projects, self.args.branch, wait_for_completion)

        if not dag.nodes:
            self.console.print("[yellow]No dependency relationships found.[/yellow]")
            return 0

        self.console.print(
            f"\n[bold cyan]Dependency Analysis - {len(dag.nodes)} packages (branch: {self.args.branch}):[/bold cyan]"
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

        if self.args.check_versions:
            self.console.print("\n[bold blue]Checking dependency versions for all packages...[/bold blue]")

            all_version_results = self.dependency_service.check_all_dependency_versions_from_dag(
                dag, self.args.branch, wait_for_completion
            )

            if all_version_results:
                self.dependency_service.display_dependency_version_verification(all_version_results, self.console)
            else:
                self.console.print("[yellow]No dependency version data found for any packages.[/yellow]")

        return 0
