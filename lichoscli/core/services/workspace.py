from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..models.workspace import Workspace


class WorkspaceService(ABC):
    """Abstract interface for branch-based workspace management operations.

    A workspace is defined by a branch name and represents all packages
    that have a branch with that name.
    """

    @abstractmethod
    def create_workspace(
        self,
        name: str,
        package_names: List[str],
    ) -> "Workspace":
        """Create a new workspace by creating branches in specified packages.

        Args:
            name: Branch name to create (workspace name)
            package_names: List of package names to create branches in

        Returns:
            Workspace instance representing the created workspace
        """

    @abstractmethod
    def add_package_to_workspace(self, workspace_name: str, package_name: str) -> bool:
        """Add a package to workspace by creating a branch with workspace name.

        Args:
            workspace_name: Name of the workspace (branch name)
            package_name: Name of the package to add

        Returns:
            True if branch was created, False if already exists
        """

    @abstractmethod
    def remove_package_from_workspace(self, workspace_name: str, package_name: str) -> bool:
        """Remove a package from workspace by deleting the branch.

        Args:
            workspace_name: Name of the workspace (branch name)
            package_name: Name of the package to remove

        Returns:
            True if branch was deleted, False if didn't exist
        """

    @abstractmethod
    def get_workspace(self, name: str) -> Optional["Workspace"]:
        """Get a workspace by checking which packages have branches with that name.

        Args:
            name: Workspace/branch name

        Returns:
            Workspace instance if any packages have that branch, None otherwise
        """

    @abstractmethod
    def list_workspaces(self) -> List["Workspace"]:
        """List all workspaces by finding all unique branch names across packages."""

    @abstractmethod
    def delete_workspace(self, name: str) -> bool:
        """Delete a workspace by removing branches with that name from all packages.

        Args:
            name: Workspace/branch name to delete

        Returns:
            True if any branches were deleted, False if workspace didn't exist
        """

    @abstractmethod
    def get_current_workspace(self) -> Optional["Workspace"]:
        """Get the currently active workspace based on LICHOS_BRANCH environment variable or current git branch."""

    @abstractmethod
    def get_workspaces_by_package(self, package_name: str) -> List["Workspace"]:
        """Get list of workspaces that contain the specified package.

        Args:
            package_name: Name of the package to search for

        Returns:
            List of Workspace objects that exist in this package
        """

    def workspace_exists(self, name: str) -> bool:
        """Check if a workspace exists (any packages have branches with that name)."""
        return self.get_workspace(name) is not None
