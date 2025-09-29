from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .variable import Variable


class Variables(ABC):
    """Abstract representation of a project variables collection."""

    @abstractmethod
    def list(self) -> List["Variable"]:
        """Get all variables in this collection."""

    @abstractmethod
    def get(self, key: str) -> Optional["Variable"]:
        """Get a specific variable by key."""

    @abstractmethod
    def create(self, key: str, value: str, **kwargs) -> "Variable":
        """Create a new variable with the given key and value."""

    @abstractmethod
    def update(self, key: str, value: str, **kwargs) -> "Variable":
        """Update an existing variable or create if it doesn't exist."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a variable by key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a variable exists by key."""

    def to_dict(self) -> dict[str, str]:
        """Convert all variables to a dictionary mapping key -> value."""
        variables = self.list()
        return {var.key: var.value for var in variables}
