# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of workspace model."""

from typing import TYPE_CHECKING

from lichoscli.core.models.workspace import Workspace

if TYPE_CHECKING:
    from lichoscli.core.models.project import Project


class GitLabWorkspace(Workspace):
    """GitLab implementation of branch-based workspace."""

    def __init__(
        self,
        name: str,
        packages: list["Project"],
        protected: bool = False,
    ):
        """Initialize GitLab workspace.

        Args:
            name: Workspace/branch name
            packages: List of package objects that have branches with this name
            protected: Whether the workspace branch is a protected branch
        """
        self._name = name
        self._packages = packages
        self._protected = protected

    @property
    def name(self) -> str:
        """Workspace name (which is also the branch name)."""
        return self._name

    @property
    def packages(self) -> list["Project"]:
        """List of package objects that have branches with this workspace name."""
        return self._packages.copy()

    @property
    def is_protected(self) -> bool:
        """Whether this workspace's branch is a protected branch."""
        return self._protected

    def __repr__(self) -> str:
        return "GitLabWorkspace(name='{0}', packages={1})".format(self.name, len(self.packages))

    def __eq__(self, other) -> bool:
        if not isinstance(other, GitLabWorkspace):
            return False
        return self.name == other.name and set(pkg.name for pkg in self.packages) == set(
            pkg.name for pkg in other.packages
        )

    def __hash__(self) -> int:
        return hash((self.name, tuple(sorted(pkg.name for pkg in self.packages))))
