from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import Pipeline


class Pipelines(ABC):
    """Abstract representation of a project pipelines collection."""

    @abstractmethod
    def get_latest(self, branch: str = None, use_cache: bool = True) -> "Pipeline | None":
        """Get the latest pipeline for a branch."""

    @abstractmethod
    def list(self, branch: str = None, **kwargs) -> list["Pipeline"]:
        """List pipelines for a branch with optional filters."""

    @abstractmethod
    def trigger_build(self, branch_name: str = None, variables: dict[str, str] = None) -> "Pipeline | None":
        """Trigger a build for a branch with optional variables."""

    @abstractmethod
    def verify_builds_success(self) -> bool:
        """Verify builds and tests for this project."""

    @abstractmethod
    def get_some_latest_pipeline(self, branch: str | None = None) -> "Pipeline | None":
        """Get the most up-to-date successful pipeline.

        Returns the latest successful pipeline from the project. If the current pipeline
        is waiting, attempts to get the previous successful pipeline.
        Always returns one pipeline for sure.

        Args:
            branch: Branch name to get pipeline from. If None, uses default branch.

        Returns:
            Pipeline: The latest available pipeline
        """
