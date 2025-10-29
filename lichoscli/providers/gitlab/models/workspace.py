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
    ):
        """Initialize GitLab workspace.

        Args:
            name: Workspace/branch name
            packages: List of package objects that have branches with this name
        """
        self._name = name
        self._packages = packages

    @property
    def name(self) -> str:
        """Workspace name (which is also the branch name)."""
        return self._name

    @property
    def packages(self) -> list["Project"]:
        """List of package objects that have branches with this workspace name."""
        return self._packages.copy()

    def __repr__(self) -> str:
        return f"GitLabWorkspace(name='{self.name}', packages={len(self.packages)})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, GitLabWorkspace):
            return False
        return self.name == other.name and set(pkg.name for pkg in self.packages) == set(
            pkg.name for pkg in other.packages
        )

    def __hash__(self) -> int:
        return hash((self.name, tuple(sorted(pkg.name for pkg in self.packages))))
