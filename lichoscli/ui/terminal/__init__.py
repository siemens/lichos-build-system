# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Built-in terminal output/prompt backend — zero external dependencies.

Inspired by the ``survey`` library (https://github.com/Exahilosys/survey).
Uses only ANSI escape sequences and ``termios`` for interactive prompts.
"""

from ._output import TerminalConsole, TerminalOutput
from ._prompts import TerminalPromptService
from ._widgets import CheckboxWidget, ConfirmWidget, SelectWidget

__all__ = [
    "CheckboxWidget",
    "ConfirmWidget",
    "SelectWidget",
    "TerminalConsole",
    "TerminalOutput",
    "TerminalPromptService",
]
