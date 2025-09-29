"""Disk-based cache service implementation using diskcache."""

import logging
from pathlib import Path
from typing import Any, Optional, Union

import diskcache as dc
from xdg import xdg_cache_home

from lichoscli.core.services import CacheService

logger = logging.getLogger(__name__)


class DiskCacheService(CacheService):
    """Disk-based cache service with TTL support using diskcache library."""

    def __init__(self, cache_dir: Optional[str] = None, default_ttl: Union[int, float] = 180):
        """
        Initialize the disk cache service.

        Args:
            cache_dir: Directory to store cache files (uses XDG cache directory if None)
            default_ttl: Default time-to-live in seconds (default: 180 = 3 minutes)
        """
        if dc is None:
            raise ImportError(
                "diskcache library is required for DiskCacheService. Install it with: pip install diskcache"
            )

        self.default_ttl = default_ttl

        if cache_dir is None:
            cache_dir = xdg_cache_home() / "lichoscli"

        cache_dir = str(cache_dir)
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        self.cache = dc.Cache(
            directory=cache_dir,
            size_limit=1024 * 1024 * 1024,
            eviction_policy="least-recently-stored",
            disk_pickle_protocol=4,
        )

        logger.debug("Initialized disk cache at %s with default TTL %ds", cache_dir, default_ttl)

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value or None if not found/expired
        """
        try:
            value = self.cache.get(key)
            if value is None:
                logger.debug("Cache miss for key: %s", key)
            return value
        except (OSError, IOError, ValueError) as e:
            logger.warning("Error reading from cache for key %s: %s", key, str(e))
            return None

    def set(self, key: str, value: Any, ttl: Optional[Union[int, float]] = None) -> None:
        """
        Set a value in the cache with optional TTL.

        Args:
            key: The cache key
            value: The value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        if ttl is None:
            ttl = self.default_ttl

        try:
            success = self.cache.set(key, value, expire=ttl)
            if not success:
                logger.warning("Failed to cache value for key: %s", key)
        except (OSError, IOError, ValueError) as e:
            logger.warning("Error writing to cache for key %s: %s", key, str(e))

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: The cache key to delete

        Returns:
            True if the key was deleted, False if it didn't exist
        """
        try:
            return self.cache.delete(key)
        except (OSError, IOError, ValueError) as e:
            logger.warning("Error deleting cache key %s: %s", key, str(e))
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        try:
            self.cache.clear()
            logger.debug("Cleared all cache entries")
        except (OSError, IOError) as e:
            logger.warning("Error clearing cache: %s", str(e))

    def stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            return {
                "size": len(self.cache),
                "volume": self.cache.volume(),
                "eviction_policy": "least-recently-stored",
                "size_limit": self.cache.size_limit,
                "default_ttl": self.default_ttl,
            }
        except (OSError, IOError, AttributeError) as e:
            logger.warning("Error getting cache stats: %s", str(e))
            return {}

    def close(self) -> None:
        """Close the cache connection."""
        try:
            self.cache.close()
            logger.debug("Closed cache connection")
        except (OSError, IOError, AttributeError) as e:
            logger.warning("Error closing cache: %s", str(e))
