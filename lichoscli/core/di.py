"""Abstract dependency injection container interface."""

from abc import ABC, abstractmethod
from typing import Type, TypeVar

T = TypeVar("T")


class DIContainer(ABC):
    """Abstract interface for dependency injection container."""

    @abstractmethod
    def obtain_ref(self, ref_type: Type[T]) -> T:
        """
        Resolve a reference instance by its type.

        Args:
            ref_type: The abstract reference type to resolve

        Returns:
            The concrete implementation of the requested reference

        Raises:
            referenceNotFoundError: If the reference type is not registered
        """
        raise NotImplementedError

    @abstractmethod
    def register_reference(self, reference_type: Type[T], implementation: T) -> None:
        """
        Register a reference implementation for a given type.

        Args:
            ref_type: The abstract reference type
            implementation: The concrete implementation instance
        """
        raise NotImplementedError


class ReferenceNotFoundError(Exception):
    """Raised when a requested reference type is not registered in the container."""
