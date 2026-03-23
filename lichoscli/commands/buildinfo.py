# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Command to list build dependencies of a package."""

import logging
import os

from lichoscli.commands.base import Command
from lichoscli.core.models import BuildDependency, BuildInfo, Project
from lichoscli.core.services import BuildInfoService, DependencyService, PackageService
from lichoscli.utils.build import BuildUtils

logger = logging.getLogger(__name__)


class BuildInfoCommand(Command):
    """List build dependencies of a package."""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.dependency_service = di_container.obtain_ref(DependencyService)
        self.buildinfo_service = di_container.obtain_ref(BuildInfoService)

    @classmethod
    def add_arguments(cls, sp):
        """Add command arguments."""
        sp.add_argument(
            "package",
            help="Package name to show dependencies for",
        )
        sp.add_argument(
            "--architecture",
            default=os.uname().machine,
            help="Architecture to fetch buildinfo for (default: host architecture)",
        )
        sp.add_argument(
            "--rev-deps",
            action="store_true",
            help="Show reverse dependencies for the specified package",
        )
        sp.add_argument(
            "--no-wait",
            action="store_true",
            help="Don't wait for pipeline completion; use latest available pipeline results",
        )

    def validate_args(self) -> None:
        """Validate command-specific arguments."""
        if not self.args.package:
            raise ValueError("Package name is required.")

    def execute(self) -> int:
        """Execute the dependencies command."""

        package: Project = self.package_service.get_package(self.args.package)
        if not package:
            self.output.error(f"Package '{self.args.package}' not found.")
            return 1

        architecture = BuildUtils.normalize_architecture(self.args.architecture)

        if self.args.rev_deps:
            return self._handle_package_rev_deps(package, architecture)

        return self._handle_dependencies(package, architecture)

    def _handle_dependencies(self, package: Project, architecture: str) -> int:
        """Handle regular forward dependencies."""

        wait_for_completion = not self.args.no_wait

        buildinfo = self.buildinfo_service.get_buildinfo(
            package, self.args.branch, wait_for_completion, architecture
        )

        if not buildinfo:
            self.output.warning(f"No buildinfo found for package '{package.name}'")
            return 0

        metadata_output = self._format_buildinfo_metadata(buildinfo)
        self.output.print(metadata_output)

        dependencies = (
            list(buildinfo.installed_build_depends.values())
            if buildinfo.installed_build_depends
            else []
        )

        if dependencies:
            output = self._format_forward_dependencies(package.name, dependencies)
            self.output.print(output)

        return 0

    def _format_forward_dependencies(
        self,
        package_name: str,
        dependencies: list[BuildDependency],
    ) -> str:
        """Format forward dependencies for display."""
        if not dependencies:
            return f"No build dependencies found for package '{package_name}'"

        lines = [
            f"\nBuild Dependencies for '{package_name}':",
            "=" * (len(package_name) + 25),
        ]

        deps_by_arch: dict[str, list[BuildDependency]] = {}
        for dep in dependencies:
            arch = dep.architecture or "all"
            if arch not in deps_by_arch:
                deps_by_arch[arch] = []
            deps_by_arch[arch].append(dep)

        for arch in sorted(deps_by_arch.keys()):
            arch_deps = deps_by_arch[arch]
            lines.extend(
                [f"\nArchitecture: {arch} ({len(arch_deps)} packages)", "-" * 40]
            )

            for dep in sorted(arch_deps, key=lambda x: x.package_name):
                dep_info = f"  • {dep.package_name}"
                if dep.version:
                    dep_info += f" (= {dep.version})"
                lines.append(dep_info)

        lines.extend(
            [
                f"\nTotal build dependencies: {len(dependencies)}",
            ]
        )

        if len(deps_by_arch) > 1:
            lines.append(f"Architectures: {', '.join(sorted(deps_by_arch.keys()))}")

        lines.append("=" * 50)

        return "\n".join(lines)

    def _format_buildinfo_metadata(self, buildinfo: BuildInfo) -> str:
        """Format buildinfo metadata for display."""
        lines = ["\nBuild Information:", "=" * 19]

        if buildinfo.format:
            lines.append(f"Format: {buildinfo.format}")

        if buildinfo.source:
            lines.append(f"Source: {buildinfo.source}")

        if buildinfo.binary:
            lines.append(f"Binary: {' '.join(buildinfo.binary)}")

        if buildinfo.architecture:
            lines.append(f"Architecture: {buildinfo.architecture}")

        if buildinfo.version:
            lines.append(f"Version: {buildinfo.version}")

        lines.append("=" * 50)
        return "\n".join(lines)

    def _handle_package_rev_deps(self, package: Project, architecture: str) -> int:
        """Handle reverse dependency operations for a specific package."""
        wait_for_completion = not self.args.no_wait

        logger.info(
            "Building dependency DAG and getting reverse dependencies for package: %s",
            package.name,
        )

        all_projects: list[Project] = self.package_service.get_packages_by_branch(
            self.args.branch
        )
        if not all_projects:
            self.output.error("No projects found in the group.")
            return 1

        logger.info("Building DAG for %d packages", len(all_projects))

        self.output.print(
            f"Building dependency Graph for branch '{self.args.branch}':"
        )

        dag = self.dependency_service.build_dependency_dag(
            all_projects, self.args.branch, wait_for_completion, architecture
        )

        if not dag.nodes:
            self.output.warning("No dependency relationships found.")
            return 0

        if package.name not in dag.nodes:
            self.output.warning(
                f"Package '{package.name}' not found in dependency graph.",
            )
            return 0

        direct_dependents = dag.nodes[package.name].reverse_dependencies
        transitive_dependents = dag.get_transitive_dependents(package.name)

        self.output.accent(
            f"\nReverse Dependencies for '{package.name}' (branch: {self.args.branch}):",
        )
        self.output.print("=" * 70)

        if not direct_dependents:
            self.output.warning(
                f"No packages depend on '{package.name}'.",
            )
            return 0

        self.output.success(
            f"\nDirect Reverse Dependencies ({len(direct_dependents)} packages):",
        )
        for dep_name in sorted(direct_dependents):
            self.output.print(f"  • {dep_name}")

        if len(transitive_dependents) > len(direct_dependents):
            self.output.warning(
                f"\nAll Dependencies (transitive, {len(transitive_dependents)} packages):",
            )

            levels = dag.group_by_depth(transitive_dependents)

            for level_index, level in enumerate(sorted(levels.keys())):
                level_nodes = levels[level]
                self.output.print(f"  Level {level_index}:")
                for node in sorted(level_nodes, key=lambda n: n.package):
                    self.output.print(f"    • {node.package}")

        return 0
