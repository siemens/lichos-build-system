# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .dag import WorkspaceStatus
    from .job import Job
    from .pipeline_status import PipelineStatus


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
    def has_any_failed(self) -> bool:
        """Return True if any job in this pipeline has failed."""

    @abstractmethod
    def aggregate_status(self) -> Optional["PipelineStatus"]:
        """Combined status of the pipeline's own jobs, ignoring external commit statuses."""

    @abstractmethod
    def workspace_status(self) -> Optional["WorkspaceStatus"]:
        """The workspace-scheduling status the scheduler posted onto this pipeline, if any."""

    @abstractmethod
    def extract_log_from_job(self, job_name: str) -> Optional[str]:
        """Extract log from a job by name."""
