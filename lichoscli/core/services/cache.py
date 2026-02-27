# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract cache service interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Union


class CacheService(ABC):
    """Abstract interface for caching service with TTL support."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value or None if not found/expired
        """
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[Union[int, float]] = None) -> None:
        """
        Set a value in the cache with optional TTL.

        Args:
            key: The cache key
            value: The value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: The cache key to delete

        Returns:
            True if the key was deleted, False if it didn't exist
        """
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Clear all entries from the cache."""
        raise NotImplementedError
