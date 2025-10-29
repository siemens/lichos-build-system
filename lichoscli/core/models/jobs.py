from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .job import Job


class Jobs(ABC):
    """Abstract representation of a pipeline jobs collection."""

    @abstractmethod
    def get_by_name(self, job_name: str) -> Optional["Job"]:
        """Find a job by name in this pipeline."""

    @abstractmethod
    def get_by_id(self, job_id: str) -> Optional["Job"]:
        """Get a job by its ID."""

    @abstractmethod
    def list(self) -> list["Job"]:
        """Get all jobs in this pipeline."""

    @abstractmethod
    def extract_log_from_job(self, job_name: str) -> Optional[str]:
        """Extract log from a job by name."""
