# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Report describing reverse build dependencies of a workspace's packages."""

from dataclasses import dataclass, field


@dataclass
class ReverseDependencyEntry:
    """A single reverse build dependency of the workspace packages."""

    name: str
    version: str
    depth: int
    in_workspace: bool


@dataclass
class ReverseDependencyReport:
    """Reverse build dependencies of a workspace, classified by membership."""

    entries: list[ReverseDependencyEntry] = field(default_factory=list)

    @property
    def in_workspace(self) -> list["ReverseDependencyEntry"]:
        """Reverse dependencies that are part of the workspace."""
        return [entry for entry in self.entries if entry.in_workspace]

    @property
    def missing(self) -> list["ReverseDependencyEntry"]:
        """Reverse dependencies that are not part of the workspace."""
        return [entry for entry in self.entries if not entry.in_workspace]
