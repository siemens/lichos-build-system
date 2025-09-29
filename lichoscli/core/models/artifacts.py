import tempfile
from abc import ABC, abstractmethod
from typing import Optional


class Artifacts(ABC):
    """Abstract representation of job artifacts.

    This class represents artifacts for a specific job, so no job identification
    parameters are needed in the methods since the instance is already scoped
    to a particular job.
    """

    @abstractmethod
    def download(self) -> Optional[bytes]:
        """Download artifacts for this job as bytes."""

    @abstractmethod
    def download_as_directory(self) -> Optional[tempfile.TemporaryDirectory]:
        """Download artifacts for this job as a temporary directory."""

    @abstractmethod
    def exists(self) -> bool:
        """Check if artifacts exist for this job."""
