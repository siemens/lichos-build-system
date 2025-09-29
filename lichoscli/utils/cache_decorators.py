"""Cache decorators for GitLab API calls."""

import functools
import logging
from typing import Any, Callable, Optional, TypeVar, Union

from cachetools import TTLCache

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def cached_property(
    cache_name: str,
    ttl: Union[int, float] = 300,
    maxsize: int = 100,
    key_func: Optional[Callable] = None,
) -> Callable[[F], F]:
    """
    Decorator for caching property values with TTL support.

    This decorator creates a class-level TTL cache for expensive property calls,
    typically GitLab API calls that don't change frequently.

    Can be used either as:
    1. @cached_property("name") - creates a property automatically
    2. @cached_property("name") + @property - works with existing property

    Args:
        cache_name: Name of the cache attribute (will be prefixed with _cache_)
        ttl: Time to live in seconds (default: 5 minutes)
        maxsize: Maximum number of cached items (default: 100)
        key_func: Optional function to generate cache key. If None, uses f"{property_name}:{self.id}"

    Returns:
        Decorated property function with caching behavior

    Example:
        @cached_property("branches", ttl=300)
        @property
        def branches(self):
            return self._project.branches

        # OR

        @cached_property("branches", ttl=300)
        def branches(self):
            return self._project.branches
    """

    def decorator(func_or_property):
        cache_attr_name = f"_cache_{cache_name}"

        if isinstance(func_or_property, property):
            original_func = func_or_property.fget
        else:
            original_func = func_or_property

        @functools.wraps(original_func)
        def wrapper(self):
            # Initialize cache if it doesn't exist
            if not hasattr(self.__class__, cache_attr_name):
                setattr(self.__class__, cache_attr_name, TTLCache(maxsize=maxsize, ttl=ttl))

            cache = getattr(self.__class__, cache_attr_name)

            if key_func:
                cache_key = key_func(self, original_func.__name__)
            else:
                cache_key = f"{original_func.__name__}:{self.id}"

            if cache_key in cache:
                logger.debug(
                    "Cache hit for %s of project %s",
                    original_func.__name__,
                    getattr(self, "path_with_namespace", "unknown"),
                )
                return cache[cache_key]

            result = original_func(self)

            cache[cache_key] = result
            logger.debug(
                "Cached %s for project %s",
                original_func.__name__,
                getattr(self, "path_with_namespace", "unknown"),
            )

            return result

        if isinstance(func_or_property, property):
            return property(
                wrapper,
                func_or_property.fset,
                func_or_property.fdel,
                func_or_property.__doc__,
            )
        return property(wrapper)

    return decorator


def clear_cache(cache_name: str, instance=None) -> None:
    """
    Clear a specific cache by name.

    Args:
        cache_name: Name of the cache to clear (without _cache_ prefix)
        instance: Optional instance to clear cache for specific item, or None to clear all
    """
    cache_attr_name = f"_cache_{cache_name}"

    for cls in [instance.__class__] if instance else []:
        if hasattr(cls, cache_attr_name):
            cache = getattr(cls, cache_attr_name)
            if instance:
                cache_key = f"{cache_name}:{instance.id}"
                if cache_key in cache:
                    del cache[cache_key]
                    logger.debug(
                        "Cleared %s cache for project %s",
                        cache_name,
                        getattr(instance, "path_with_namespace", "unknown"),
                    )
            else:
                cache.clear()
                logger.debug("Cleared all %s cache", cache_name)
            break


def clear_all_caches(cls) -> None:
    """
    Clear all caches for a class.

    Args:
        cls: The class to clear caches for
    """
    cache_attrs = [attr for attr in dir(cls) if attr.startswith("_cache_")]
    for cache_attr in cache_attrs:
        cache = getattr(cls, cache_attr)
        cache.clear()
        cache_name = cache_attr.replace("_cache_", "")
        logger.debug("Cleared all %s cache", cache_name)


def cached_method(
    cache_name: str,
    ttl: Union[int, float] = 300,
    maxsize: int = 100,
    key_func: Optional[Callable] = None,
) -> Callable[[F], F]:
    """
    Decorator for caching method return values with TTL support.

    Similar to cached_property but for methods that take parameters.

    Args:
        cache_name: Name of the cache attribute (will be prefixed with _cache_)
        ttl: Time to live in seconds (default: 5 minutes)
        maxsize: Maximum number of cached items (default: 100)
        key_func: Optional function to generate cache key. If None, uses method name and args

    Returns:
        Decorated method function with caching behavior

    Example:
        @cached_method("latest_pipeline", ttl=180)
        def get_latest(self, branch=None):
            return self._fetch_latest_pipeline(branch)
    """

    def decorator(func: F) -> F:
        cache_attr_name = f"_cache_{cache_name}"

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not hasattr(self.__class__, cache_attr_name):
                setattr(self.__class__, cache_attr_name, TTLCache(maxsize=maxsize, ttl=ttl))

            cache = getattr(self.__class__, cache_attr_name)

            if key_func:
                cache_key = key_func(self, func.__name__, *args, **kwargs)
            else:
                args_str = "_".join(str(arg) for arg in args)
                kwargs_str = "_".join(f"{k}:{v}" for k, v in sorted(kwargs.items()))
                key_parts = [
                    func.__name__,
                    str(getattr(self, "id", "no_id")),
                    args_str,
                    kwargs_str,
                ]
                cache_key = ":".join(filter(None, key_parts))

            if cache_key in cache:
                logger.debug("Cache hit for %s with key %s", func.__name__, cache_key)
                return cache[cache_key]

            result = func(self, *args, **kwargs)

            cache[cache_key] = result
            logger.debug("Cached %s with key %s", func.__name__, cache_key)

            return result

        return wrapper

    return decorator


class CacheMixin:
    """Mixin class providing cache management methods."""

    def clear_cache(self, cache_name: str) -> None:
        """Clear cache for this instance."""
        clear_cache(cache_name, self)

    def clear_all_caches(self) -> None:
        """Clear all caches for this instance."""
        cache_attrs = [attr for attr in dir(self.__class__) if attr.startswith("_cache_")]
        for cache_attr in cache_attrs:
            cache_name = cache_attr.replace("_cache_", "")
            self.clear_cache(cache_name)

    @classmethod
    def clear_all_class_caches(cls) -> None:
        """Clear all caches for this class."""
        clear_all_caches(cls)
