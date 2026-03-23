# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from __future__ import annotations

from enum import Enum

from .interfaces import OutputWriter, PromptService, UserInterface
from .terminal import TerminalOutput, TerminalPromptService


class OutputBackend(str, Enum):
    """Supported output rendering backends."""

    TERMINAL = "terminal"


class PromptBackend(str, Enum):
    """Supported interactive prompt backends."""

    TERMINAL = "terminal"


class UserInterfaceFactory:
    """Create UI abstractions from configurable backend selections."""

    @staticmethod
    def _create_output(backend: OutputBackend) -> OutputWriter:
        if backend == OutputBackend.TERMINAL:
            return TerminalOutput()
        raise ValueError(f"Unsupported output backend: {backend}")

    @staticmethod
    def _create_prompts(backend: PromptBackend, output: OutputWriter) -> PromptService:
        if backend == PromptBackend.TERMINAL:
            return TerminalPromptService(output)
        raise ValueError(f"Unsupported prompt backend: {backend}")

    @staticmethod
    def create(
        output_backend: OutputBackend = OutputBackend.TERMINAL,
        prompt_backend: PromptBackend = PromptBackend.TERMINAL,
    ) -> UserInterface:
        output = UserInterfaceFactory._create_output(output_backend)
        prompts = UserInterfaceFactory._create_prompts(prompt_backend, output)
        return UserInterface(output=output, prompts=prompts)


