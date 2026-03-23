# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol

from .models import Choice, Table, Tree


class StatusDisplay(Protocol):
    """Minimal status handle used by legacy command code."""

    def __enter__(self) -> StatusDisplay:
        """Enter the status context."""

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the status context."""

    def start(self) -> None:
        """Resume the status indicator."""

    def stop(self) -> None:
        """Pause the status indicator."""


class ConsoleLike(Protocol):
    """Compatibility surface for commands that still use self.console directly."""

    def print(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print objects to the console."""

    def info(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print informational objects."""

    def warning(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print cautionary objects."""

    def error(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print error objects."""

    def success(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print success objects."""

    def accent(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print emphasized objects."""

    def muted(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print secondary objects."""

    def danger(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        """Print warning-semantics objects."""

    def print_json(self, *, data: Any, **kwargs: Any) -> None:
        """Render JSON content."""

    def status(self, status: str, **kwargs: Any) -> StatusDisplay:
        """Create a status context manager."""


class OutputWriter(ABC):
    """Abstract output surface for CLI presentation concerns."""

    @property
    @abstractmethod
    def console(self) -> ConsoleLike:
        """Compatibility console for legacy command code during migration."""

    @abstractmethod
    def print(
        self,
        message: str = "",
        end: str = "\n",
    ) -> None:
        """Print plain text without additional styling."""

    @abstractmethod
    def _print_styled(
        self,
        message: str = "",
        style: str = "info",
        end: str = "\n",
    ) -> None:
        """Render text with a named output style."""

    def info(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Print informational output."""
        self._print_styled(message, style="info", end=end)

    def warning(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Print cautionary output."""
        self._print_styled(message, style="warning", end=end)

    def error(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Print error output."""
        self._print_styled(message, style="error", end=end)

    def success(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Print success output."""
        self._print_styled(message, style="success", end=end)

    def accent(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Print emphasized section output."""
        self._print_styled(message, style="accent", end=end)

    def muted(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Print secondary or background output."""
        self._print_styled(message, style="muted", end=end)

    def danger(
        self,
        message: str = "",
        *,
        end: str = "\n",
    ) -> None:
        """Compatibility alias for legacy danger output, now rendered as warning semantics."""
        self.warning(message, end=end)

    @abstractmethod
    def table(self, table: Table) -> None:
        """Render structured tabular data."""

    @abstractmethod
    def tree(self, tree: Tree) -> None:
        """Render a structured tree."""

    @abstractmethod
    def json(self, data: Any) -> None:
        """Render JSON data."""


class PromptService(ABC):
    """Abstract prompt surface for interactive CLI flows."""

    @abstractmethod
    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for a yes/no answer."""

    @abstractmethod
    def select_one(self, title: str, text: str, choices: list[Choice]) -> str | None:
        """Select a single choice or return None when cancelled."""

    @abstractmethod
    def select_many(self, title: str, text: str, choices: list[Choice]) -> list[str] | None:
        """Select multiple choices or return None when cancelled."""

    @abstractmethod
    def text_input(self, message: str, default: str | None = None) -> str | None:
        """Prompt for free-form text input."""

    @abstractmethod
    def secret_input(self, message: str) -> str | None:
        """Prompt for sensitive input (e.g. a token) without echoing characters."""


@dataclass(frozen=True)
class UserInterface:
    """Aggregates output and prompt abstractions for command execution."""

    output: OutputWriter
    prompts: PromptService
