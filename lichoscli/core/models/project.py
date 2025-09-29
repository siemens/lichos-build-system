from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .merge_requests import MergeRequests
    from .pipelines import Pipelines
    from .tags import Tags
    from .variables import Variables


class Project(ABC):
    """Abstract representation of a project/repository."""

    @property
    @abstractmethod
    def id(self) -> int:
        """Project ID."""

    @property
    @abstractmethod
    def path(self) -> str:
        """Project path (short name)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Project name."""

    @property
    @abstractmethod
    def path_with_namespace(self) -> str:
        """Full path including namespace."""

    @property
    @abstractmethod
    def web_url(self) -> str:
        """Web URL to project."""

    @property
    @abstractmethod
    def default_branch(self) -> str:
        """Default branch name."""

    @property
    @abstractmethod
    def ci_config_path(self) -> Optional[str]:
        """CI configuration file path."""

    @property
    @abstractmethod
    def archived(self) -> bool:
        """Whether project is archived."""

    @property
    @abstractmethod
    def builds_access_level(self) -> Optional[str]:
        """Build access level."""

    @property
    @abstractmethod
    def ssh_url_to_repo(self) -> str:
        """SSH URL for cloning the repository."""

    @property
    @abstractmethod
    def is_fork(self) -> bool:
        """Whether this project is a fork of another project."""

    @property
    @abstractmethod
    def parent_project_namespace(self) -> Optional[str]:
        """The full namespace path of the parent project if this is a fork."""

    @property
    @abstractmethod
    def parent_ssh_url_to_repo(self) -> Optional[str]:
        """SSH URL of the parent project if this is a fork, None otherwise."""

    @property
    @abstractmethod
    def attributes(self) -> Dict[str, Any]:
        """Project attributes including forked_from_project."""

    @property
    @abstractmethod
    def namespace(self) -> Dict[str, Any]:
        """Project namespace information."""

    @property
    @abstractmethod
    def variables(self) -> "Variables":
        """Project variables collection."""

    @property
    @abstractmethod
    def branches(self):
        """Project branches manager."""

    @property
    @abstractmethod
    def protectedbranches(self):
        """Project protected branches manager."""

    @property
    @abstractmethod
    def tags(self) -> "Tags":
        """Project tags collection."""

    @property
    @abstractmethod
    def pipelines(self) -> "Pipelines":
        """Project pipelines collection."""

    @property
    @abstractmethod
    def merge_requests(self) -> "MergeRequests":
        """Project merge requests collection."""

    @property
    @abstractmethod
    def forks(self):
        """Project forks manager."""

    @abstractmethod
    def has_branch(self, branch_name: str) -> bool:
        """Check if the project has a branch with the given name.

        Args:
            branch_name: Name of the branch to check for

        Returns:
            True if the branch exists, False otherwise
        """

    @abstractmethod
    def save(self):
        """Save changes to the project."""

    @abstractmethod
    def create_fork_relation(self, parent_id: int):
        """Create a fork relationship with a parent project."""

    @abstractmethod
    def fork_to(self, target_namespace: str, subgroup: Optional[str] = None) -> Optional["Project"]:
        """Fork this project to a target namespace with optional subgroup.

        Args:
            target_namespace: The namespace path to fork to
            subgroup: Optional subgroup within the target namespace

        Returns:
            The forked project if successful, None otherwise
        """

    @abstractmethod
    def get_latest_commit_sha(self, branch: str) -> Optional[str]:
        """Get the latest commit SHA for a given branch.

        Args:
            branch: The branch name to get the latest commit SHA from

        Returns:
            The latest commit SHA if successful, None otherwise
        """
