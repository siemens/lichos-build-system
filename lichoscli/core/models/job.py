# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .artifacts import Artifacts
    from .pipeline import Pipeline


class Job(ABC):
    """Abstract representation of a CI/CD job."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Job ID."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Job name."""

    @property
    @abstractmethod
    def status(self) -> str:
        """Job status."""

    @property
    @abstractmethod
    def web_url(self) -> str:
        """Job web URL."""

    @property
    @abstractmethod
    def stage(self) -> str:
        """Job stage."""

    @property
    @abstractmethod
    def started_at(self) -> Optional[str]:
        """Job start timestamp."""

    @property
    @abstractmethod
    def finished_at(self) -> Optional[str]:
        """Job finish timestamp."""

    @property
    @abstractmethod
    def pipeline(self) -> "Pipeline":
        """Parent pipeline of this job."""

    @property
    @abstractmethod
    def artifacts(self) -> "Artifacts":
        """Job artifacts collection."""

    @abstractmethod
    def get_trace(self) -> Optional[str]:
        """Get job execution log."""

    @abstractmethod
    def get_artifacts(self) -> Optional[bytes]:
        """Download job artifacts."""

    @abstractmethod
    def retry(self) -> bool:
        """Retry the job."""

    @abstractmethod
    def cancel(self) -> bool:
        """Cancel the job."""

    def to_dict(self) -> dict:
        """Convert job to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "web_url": self.web_url,
            "stage": self.stage,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
