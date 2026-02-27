# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from typing import Optional


class Variable(ABC):
    """Abstract representation of a project variable."""

    @property
    @abstractmethod
    def key(self) -> str:
        """Variable key/name."""

    @property
    @abstractmethod
    def value(self) -> str:
        """Variable value."""

    @property
    @abstractmethod
    def variable_type(self) -> str:
        """Variable type (env_var, file)."""

    @property
    @abstractmethod
    def protected(self) -> bool:
        """Whether variable is protected."""

    @property
    @abstractmethod
    def masked(self) -> bool:
        """Whether variable is masked."""

    @property
    @abstractmethod
    def environment_scope(self) -> Optional[str]:
        """Environment scope for the variable."""

    @property
    @abstractmethod
    def raw(self) -> bool:
        """Whether variable is raw (unprocessed)."""

    @property
    @abstractmethod
    def description(self) -> Optional[str]:
        """Variable description."""

    @property
    @abstractmethod
    def inherited(self) -> bool:
        """Whether variable is inherited from a parent group."""

    @abstractmethod
    def save(self):
        """Save changes to the variable."""

    @abstractmethod
    def delete(self):
        """Delete the variable."""
