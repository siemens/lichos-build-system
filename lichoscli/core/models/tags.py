# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .tag import Tag


class Tags(ABC):
    """Abstract representation of a project tags collection."""

    @abstractmethod
    def list(self) -> list["Tag"]:
        """Get all tags in this collection."""

    @abstractmethod
    def get(self, name: str) -> Optional["Tag"]:
        """Get a specific tag by name."""

    @abstractmethod
    def create(self, name: str, target: str, message: Optional[str] = None) -> "Tag":
        """Create a new tag."""

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Delete a tag by name."""

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Check if a tag exists by name."""
