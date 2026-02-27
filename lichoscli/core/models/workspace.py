# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .project import Project


class Workspace(ABC):
    """Abstract representation of a branch-based workspace.

    A workspace is defined by a branch name and represents all packages
    that have a branch with that name.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Workspace name (which is also the branch name)."""

    @property
    @abstractmethod
    def packages(self) -> list["Project"]:
        """List of package objects that have branches with this workspace name."""
