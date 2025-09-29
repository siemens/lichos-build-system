from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .job import Job
    from .merge_request import MergeRequest


class MergeRequests(ABC):
    """Abstract representation of a project merge requests collection."""

    @abstractmethod
    def list(
        self,
        state: str = "opened",
        branch_name: Optional[str] = None,
        get_all: bool = False,
    ) -> List["MergeRequest"]:
        """Get merge requests in this collection."""

    @abstractmethod
    def get(self, mr_iid: str) -> Optional["MergeRequest"]:
        """Get a specific merge request by IID."""

    @abstractmethod
    def get_job_by_name_from_mr(self, job_name: str, branch: Optional[str] = None) -> Optional["Job"]:
        """Find a job by name in merge request pipeline."""

    @abstractmethod
    def extract_log_from_job_mr(self, job_name: str, branch: Optional[str] = None) -> Optional[str]:
        """Extract log from a job in merge request pipeline."""
