# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""PromptService backed by the terminal widgets (no external deps)."""

from __future__ import annotations

import getpass
from typing import Optional

from . import _ansi
from ._output import TerminalOutput
from ._widgets import CheckboxWidget, ConfirmWidget, SelectWidget
from ..interfaces import PromptService
from ..models import Choice


class TerminalPromptService(PromptService):
    """Interactive prompt backend using built-in ANSI widgets."""

    def __init__(self, output: TerminalOutput) -> None:
        self._output = output

    def confirm(self, message: str, default: bool = False) -> bool:
        widget = ConfirmWidget(
            message,
            default=default,
            stream=self._output._stream,
        )
        result = widget.run()
        if result is None:
            return False
        return result

    def select_one(
        self,
        title: str,
        text: str,
        choices: list[Choice],
    ) -> Optional[str]:
        if title:
            self._output.print(_ansi.paint(title, _ansi.BOLD, _ansi.FG_YELLOW))
        if text:
            self._output.print(text)

        labels = [c.label for c in choices]
        widget = SelectWidget(
            labels,
            stream=self._output._stream,
        )
        index = widget.run()
        if index is None:
            return None
        return choices[index].value

    def select_many(
        self,
        title: str,
        text: str,
        choices: list[Choice],
    ) -> Optional[list[str]]:
        if title:
            self._output.print(_ansi.paint(title, _ansi.BOLD, _ansi.FG_YELLOW))
        if text:
            self._output.print(text)

        labels = [c.label for c in choices]
        widget = CheckboxWidget(
            labels,
            stream=self._output._stream,
        )
        selected = widget.run()
        if selected is None:
            return None
        return [choices[i].value for i in sorted(selected)]

    def text_input(self, message: str, default: Optional[str] = None) -> Optional[str]:
        if default is not None:
            prompt = _ansi.paint("{0} [{1}]: ".format(message, default), _ansi.BOLD)
        else:
            prompt = _ansi.paint("{0}: ".format(message), _ansi.BOLD)
        self._output._stream.write(prompt)
        self._output._stream.flush()
        try:
            value = input("")
        except (EOFError, KeyboardInterrupt):
            self._output.print("")
            return default
        value = value.strip()
        return value if value else default

    def secret_input(self, message: str) -> Optional[str]:
        prompt = _ansi.paint("{0}: ".format(message), _ansi.BOLD)
        self._output._stream.write(prompt)
        self._output._stream.flush()
        try:
            value = getpass.getpass(prompt="")
        except (EOFError, KeyboardInterrupt):
            self._output.print("")
            return None
        value = value.strip()
        return value if value else None
