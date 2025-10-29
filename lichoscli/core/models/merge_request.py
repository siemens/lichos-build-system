from abc import ABC, abstractmethod
from typing import Any


class MergeRequest(ABC):
    """Abstract representation of a merge/pull request."""

    @property
    @abstractmethod
    def iid(self) -> str:
        """Internal ID."""

    @property
    @abstractmethod
    def title(self) -> str:
        """MR title."""

    @property
    @abstractmethod
    def author(self) -> dict[str, Any]:
        """MR author information."""

    @property
    @abstractmethod
    def created_at(self) -> str:
        """Creation timestamp."""

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

    @abstractmethod
    def create_pipeline(self) -> int:
        """Create/trigger a pipeline for this merge request.

        Returns:
            Pipeline ID on success, raises exception on failure.
        """

    @abstractmethod
    def merge(self) -> bool:
        """Merge this merge request.

        Returns:
            True if merge was successful, False otherwise.
        """
