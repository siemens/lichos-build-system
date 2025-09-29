from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .project import Project


class Projects(ABC):
    """Abstract representation of a project collection."""

    @property
    @abstractmethod
    def path(self) -> str:
        """Get the path/namespace of this project collection."""

    @abstractmethod
    def get(self, name: str) -> Optional["Project"]:
        """Get a specific project by name."""

    @abstractmethod
    def get_projects_for_namespace(self, namespace_path: str) -> Optional["Projects"]:
        """Get projects collection for a group by namespace path.

        Args:
            namespace_path: The namespace path to get projects for

        Returns:
            Projects collection if namespace exists, None otherwise
        """

    @abstractmethod
    def hierarchy_exists(self, target_path: str) -> bool:
        """Check if a hierarchy exists at the target path.

        Args:
            target_path: Path to check for existence

        Returns:
            True if hierarchy exists, False otherwise
        """

    def get_group_id(self, namespace_path: str) -> Optional[int]:
        """Get group ID for a namespace path."""
