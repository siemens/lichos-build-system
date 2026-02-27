# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional


class Tag(ABC):
    """Abstract representation of a project tag."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tag name."""

    @property
    @abstractmethod
    def target(self) -> str:
        """Target commit SHA."""

    @property
    @abstractmethod
    def message(self) -> Optional[str]:
        """Tag message."""

    @property
    @abstractmethod
    def protected(self) -> bool:
        """Whether tag is protected."""

    @property
    @abstractmethod
    def created_at(self) -> Optional[datetime]:
        """Tag creation timestamp."""

    @property
    @abstractmethod
    def commit(self) -> dict[str, Any]:
        """Commit information for this tag."""

    @property
    @abstractmethod
    def release(self) -> Optional[dict[str, Any]]:
        """Release information if this tag has an associated release."""

    @abstractmethod
    def delete(self):
        """Delete the tag."""
