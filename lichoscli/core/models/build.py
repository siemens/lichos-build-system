# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from dataclasses import dataclass
from typing import Optional


@dataclass
class BuildParameters:
    """Configuration for building a package locally."""

    package_name: str
    architecture: str
    branch: str = "main"
    group: Optional[str] = None
    project_dir: str = "/build"
    platform: Optional[str] = None
    enable_cross: bool = False
    profile: Optional[str] = None
    network: Optional[str] = None
    mount: Optional[str] = None
    shell_mode: bool = False
    editor_mode: bool = False
    no_cache: bool = False
    privileged: bool = False
    custom_script: Optional[str] = None


@dataclass
class BuildDependency:
    """Represents a build dependency with version information."""

    package_name: str
    version: str
    architecture: str


@dataclass
class ReverseDependency:
    """Represents a reverse build dependency - packages that depend on this package."""

    package: str
    dependent_package: str
    version: str
    depth: int = 1


@dataclass
class BuildInfo:
    """Represents build information parsed from buildinfo files."""

    format: str
    source: str
    binary: list[str]
    architecture: str
    version: str
    installed_build_depends: dict[str, BuildDependency]

    def has_build_dependency(self, package_name: str) -> bool:
        """Check if a package is in build dependencies (fast O(1) lookup)."""
        return package_name in self.installed_build_depends

    def get_build_dependency(self, package_name: str) -> Optional[BuildDependency]:
        """Get build dependency by package name (fast O(1) lookup)."""
        return self.installed_build_depends.get(package_name)
