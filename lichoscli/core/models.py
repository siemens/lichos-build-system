from abc import ABC, abstractmethod
from typing import Optional


class Project(ABC):
    """Abstract representation of a project/repository."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Project unique identifier."""

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


class MergeRequest(ABC):
    """Abstract representation of a merge/pull request."""

    @property
    @abstractmethod
    def id(self) -> str:
        """MR unique identifier."""

    @property
    @abstractmethod
    def iid(self) -> str:
        """Internal ID."""

    @property
    @abstractmethod
    def source_branch(self) -> str:
        """Source branch name."""

    @property
    @abstractmethod
    def target_branch(self) -> str:
        """Target branch name."""

    @property
    @abstractmethod
    def web_url(self) -> str:
        """Web URL to MR."""

    @property
    @abstractmethod
    def state(self) -> str:
        """MR state (opened, closed, merged)."""


class Pipeline(ABC):
    """Abstract representation of a CI/CD pipeline."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Pipeline unique identifier."""

    @property
    @abstractmethod
    def status(self) -> str:
        """Pipeline status."""

    @property
    @abstractmethod
    def ref(self) -> str:
        """Git reference (branch/tag)."""

    @property
    @abstractmethod
    def web_url(self) -> str:
        """Web URL to pipeline."""


class Job(ABC):
    """Abstract representation of a CI/CD job."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Job unique identifier."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Job name."""

    @property
    @abstractmethod
    def status(self) -> str:
        """Job status."""

    @abstractmethod
    def get_trace(self) -> Optional[str]:
        """Get job execution log."""

    @abstractmethod
    def get_artifacts(self) -> Optional[bytes]:
        """Download job artifacts."""


class Group(ABC):
    """Abstract representation of a group/organization."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Group unique identifier."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Group name."""

    @property
    @abstractmethod
    def path(self) -> str:
        """Group path."""

    @property
    @abstractmethod
    def full_path(self) -> str:
        """Full path including parent groups."""
