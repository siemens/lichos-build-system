# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""ANSI escape sequence helpers for terminal rendering."""

# Reset
RESET = "\033[0m"

# Text attributes
BOLD = "\033[1m"
DIM = "\033[2m"

# Foreground colors
FG_RED = "\033[31m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_BLUE = "\033[34m"
FG_MAGENTA = "\033[35m"
FG_CYAN = "\033[36m"
FG_WHITE = "\033[37m"


def move_up(n: int = 1) -> str:
    """Move cursor up n lines."""
    return f"\033[{n}A" if n else ""


def move_down(n: int = 1) -> str:
    """Move cursor down n lines."""
    return f"\033[{n}B" if n else ""


def move_to_column(n: int = 0) -> str:
    """Move cursor to column n (0-based)."""
    return f"\033[{n + 1}G"


def clear_line() -> str:
    """Clear entire current line."""
    return "\033[2K"


def clear_to_end_of_line() -> str:
    """Clear from cursor to end of line."""
    return "\033[0K"


def clear_below() -> str:
    """Clear from cursor to end of screen."""
    return "\033[J"


def hide_cursor() -> str:
    """Hide the terminal cursor."""
    return "\033[?25l"


def show_cursor() -> str:
    """Show the terminal cursor."""
    return "\033[?25h"


def paint(text: str, *codes: str) -> str:
    """Wrap text with ANSI codes and reset."""
    if not codes:
        return text
    prefix = "".join(codes)
    return f"{prefix}{text}{RESET}"
