# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract interface for discovering package groups on a provider."""

from abc import ABC, abstractmethod
from typing import List, Optional


class PkgGroupDiscoveryService(ABC):
    """Discover and manage package group paths on a provider."""

    @abstractmethod
    def search_pkg_groups(self, query: str, host: Optional[str] = None) -> List[str]:
        """Return a list of group paths whose namespace contains a project matching *query*."""

    def exists(self, pkg_group_path: str, query: str, host: Optional[str] = None) -> bool:
        """Return True when *pkg_group_path* appears as an exact match in the discovery results."""
        return pkg_group_path in self.search_pkg_groups(query, host=host)

    @abstractmethod
    def get_group_id(self, group_path: str) -> Optional[int]:
        """Return the numeric ID of a group, or None if it does not exist."""

    @abstractmethod
    def create_group(
        self,
        name: str,
        path: str,
        parent_id: Optional[int] = None,
        description: str = "",
        visibility: str = "internal",
    ) -> int:
        """Create a new group and return its numeric ID."""
