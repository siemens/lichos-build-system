"""Abstract User model for CI/CD users."""

from abc import ABC, abstractmethod
from typing import Optional


class User(ABC):
    """Abstract representation of a CI/CD user."""

    @property
    @abstractmethod
    def id(self) -> int:
        """User ID."""

    @property
    @abstractmethod
    def username(self) -> str:
        """Username."""

    @property
    @abstractmethod
    def name(self) -> Optional[str]:
        """Full name of the user."""

    @property
    @abstractmethod
    def email(self) -> Optional[str]:
        """Email address of the user."""

    @property
    @abstractmethod
    def web_url(self) -> Optional[str]:
        """Web URL to user profile."""

    def to_dict(self) -> dict:
        """Convert user to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "email": self.email,
            "web_url": self.web_url,
        }
