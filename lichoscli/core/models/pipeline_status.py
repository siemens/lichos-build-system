# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Pipeline status enumeration and utilities."""

from enum import Enum


class PipelineStatus(Enum):
    """Pipeline status enumeration with semantic groupings."""

    CREATED = "created"
    WAITING_FOR_RESOURCE = "waiting_for_resource"
    PREPARING = "preparing"
    PENDING = "pending"
    SCHEDULED = "scheduled"

    RUNNING = "running"
    MANUAL = "manual"

    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    CANCELING = "canceling"
    SKIPPED = "skipped"

    @property
    def is_waiting(self) -> bool:
        """True if pipeline is waiting to start or in preparation."""
        return self in {
            PipelineStatus.CREATED,
            PipelineStatus.WAITING_FOR_RESOURCE,
            PipelineStatus.PREPARING,
            PipelineStatus.PENDING,
            PipelineStatus.SCHEDULED,
        }

    @property
    def is_active(self) -> bool:
        """True if pipeline is currently running or needs manual intervention."""
        return self in {
            PipelineStatus.RUNNING,
            PipelineStatus.MANUAL,
        }

    @property
    def is_final(self) -> bool:
        """True if pipeline has completed (successfully or not)."""
        return self in {
            PipelineStatus.SUCCESS,
            PipelineStatus.FAILED,
            PipelineStatus.CANCELED,
            PipelineStatus.CANCELING,
            PipelineStatus.SKIPPED,
        }

    @property
    def is_successful(self) -> bool:
        """True if pipeline completed successfully."""
        return self == PipelineStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """True if pipeline failed, was canceled, or is being canceled."""
        return self in {
            PipelineStatus.FAILED,
            PipelineStatus.CANCELED,
            PipelineStatus.CANCELING,
        }

    @classmethod
    def waiting_states(cls) -> set["PipelineStatus"]:
        """Get all waiting/preparation status values."""
        return {
            cls.CREATED,
            cls.WAITING_FOR_RESOURCE,
            cls.PREPARING,
            cls.PENDING,
            cls.SCHEDULED,
        }

    @classmethod
    def active_states(cls) -> set["PipelineStatus"]:
        """Get all active status values."""
        return {
            cls.RUNNING,
            cls.MANUAL,
        }

    @classmethod
    def final_states(cls) -> set["PipelineStatus"]:
        """Get all final status values."""
        return {
            cls.SUCCESS,
            cls.FAILED,
            cls.CANCELED,
            cls.CANCELING,
            cls.SKIPPED,
        }

    @classmethod
    def from_string(cls, status_str: str) -> "PipelineStatus":
        """
        Create PipelineStatus from string value.

        Args:
            status_str: Raw status string from provider

        Returns:
            PipelineStatus enum value

        Raises:
            ValueError: If status string is not recognized
        """
        try:
            return cls(status_str)
        except ValueError as exc:
            raise ValueError(f"Unknown pipeline status: {status_str}") from exc

    def __str__(self) -> str:
        """Return the string value of the status."""
        return self.value

    def to_string(self) -> str:
        """Convert to string representation."""
        return self.value

    def to_display_string(self) -> str:
        """Convert to colored string for display in terminal."""
        match self:
            case PipelineStatus.FAILED | PipelineStatus.CANCELED | PipelineStatus.CANCELING:
                return f"[red]{self.value}[/red]"
            case PipelineStatus.SUCCESS:
                return f"[green]{self.value}[/green]"
            case PipelineStatus.RUNNING | PipelineStatus.MANUAL:
                return f"[yellow]{self.value}[/yellow]"
            case _:
                return self.value
