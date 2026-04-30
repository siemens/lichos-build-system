# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from .pipeline_status import PipelineStatus
from lichoscli.utils.constants import CI_PUBLISH_JOB_NAME

if TYPE_CHECKING:
    from .jobs import Jobs
    from .project import Project
    from .user import User


class Pipeline(ABC):
    """Abstract representation of a CI/CD pipeline."""

    @property
    @abstractmethod
    def id(self) -> int:
        """Pipeline ID."""

    @property
    @abstractmethod
    def status(self) -> PipelineStatus:
        """Pipeline status as enum value."""

    @property
    @abstractmethod
    def ref(self) -> str:
        """Git reference (branch/tag)."""

    @property
    @abstractmethod
    def web_url(self) -> str:
        """Web URL to pipeline."""

    @property
    @abstractmethod
    def updated_at(self) -> str:
        """Pipeline last update timestamp."""

    @property
    @abstractmethod
    def sha(self) -> str:
        """Git commit SHA that triggered the pipeline."""

    @property
    @abstractmethod
    def source(self) -> str:
        """Pipeline source (push, web, merge_request_event, etc.)."""

    @property
    @abstractmethod
    def user(self) -> Optional["User"]:
        """User who triggered the pipeline."""

    @property
    @abstractmethod
    def project(self) -> "Project":
        """Parent project of this pipeline."""

    @property
    @abstractmethod
    def jobs(self) -> "Jobs":
        """Access to pipeline jobs collection."""

    @abstractmethod
    def retry(self) -> bool:
        """Retry the pipeline."""

    @abstractmethod
    def cancel(self) -> bool:
        """Cancel the pipeline."""

    def is_publish_complete(self) -> bool:
        """Return True when the publish job has completed successfully."""
        job = self.jobs.get_by_name(CI_PUBLISH_JOB_NAME)
        return job is not None and job.status == "success"

    def is_successful(self) -> bool:
        """Return True when this pipeline has produced usable artifacts."""
        return self.is_publish_complete()

    def has_failed_jobs(self) -> bool:
        """Return True if any job in this pipeline has failed."""
        return self.jobs.has_any_failed()

    def to_dict(self) -> dict:
        """Convert pipeline to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "status": self.status.to_string(),
            "ref": self.ref,
            "web_url": self.web_url,
            "updated_at": self.updated_at,
            "sha": self.sha,
            "source": self.source,
        }
