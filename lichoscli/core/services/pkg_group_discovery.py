# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract interface for discovering package groups on a provider."""

from abc import ABC, abstractmethod
from typing import List, Optional


class PkgGroupDiscoveryService(ABC):
    """Discover package group paths by searching for a query project name."""

    @abstractmethod
    def search_pkg_groups(self, query: str, host: Optional[str] = None) -> List[str]:
        """Return a list of group paths whose namespace contains a project matching *query*."""
