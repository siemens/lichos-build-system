# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Raw terminal mode and keypress reading (POSIX only)."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from contextlib import contextmanager
from typing import TextIO

# Symbolic key names
KEY_UP = "up"
KEY_DOWN = "down"
KEY_LEFT = "left"
KEY_RIGHT = "right"
KEY_ENTER = "enter"
KEY_SPACE = "space"
KEY_TAB = "tab"
KEY_ESCAPE = "escape"
KEY_BACKSPACE = "backspace"
KEY_DELETE = "delete"
KEY_RESIZE = "resize"


@contextmanager
def raw_mode(stream: TextIO | None = None):
    """Context manager that puts the terminal into raw (cbreak) mode.

    Restores original settings on exit, even after exceptions.
    """
    fd = (stream or sys.stdin).fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, old_settings)


def _read_char(stream: TextIO) -> str:
    """Read a single character from the stream."""
    return stream.read(1)


def read_key(stream: TextIO | None = None) -> str:
    """Read a single keypress and return a symbolic key name.

    Must be called while in raw_mode.  Returns one of the KEY_* constants
    or the literal character for printable keys.
    """
    stdin = stream or sys.stdin
    ch = _read_char(stdin)

    if ch == "\x1b":
        # Escape sequence
        ch2 = _read_char(stdin)
        if ch2 == "[":
            ch3 = _read_char(stdin)
            if ch3 == "A":
                return KEY_UP
            if ch3 == "B":
                return KEY_DOWN
            if ch3 == "C":
                return KEY_RIGHT
            if ch3 == "D":
                return KEY_LEFT
            if ch3 == "3":
                # Delete key: ESC [ 3 ~
                ch4 = _read_char(stdin)
                if ch4 == "~":
                    return KEY_DELETE
            # Unknown sequence – swallow
            return KEY_ESCAPE
        # Bare ESC or Alt+key
        return KEY_ESCAPE

    if ch in ("\r", "\n"):
        return KEY_ENTER
    if ch == " ":
        return KEY_SPACE
    if ch == "\t":
        return KEY_TAB
    if ch in ("\x7f", "\x08"):
        return KEY_BACKSPACE

    # Ctrl+C / Ctrl+D → raise so callers can handle
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch == "\x04":
        raise EOFError

    return ch


def read_key_or_resize(stream: TextIO, resize_fd: int = -1) -> str:
    """Like :func:`read_key` but also monitors *resize_fd* for SIGWINCH.

    When the pipe read-end *resize_fd* becomes readable (written to by a
    SIGWINCH handler), all queued bytes are drained and ``KEY_RESIZE`` is
    returned.  If *resize_fd* is ``-1`` (default), this is identical to
    :func:`read_key`.

    Must be called while in :func:`raw_mode`.
    """
    if resize_fd < 0:
        return read_key(stream)

    stdin_fd = stream.fileno()
    while True:
        try:
            readable, _, _ = select.select([stdin_fd, resize_fd], [], [])
        except InterruptedError:
            # Retry after any signal that interrupted select (belt-and-braces;
            # PEP 475 already handles EINTR in most system calls).
            continue

        if resize_fd in readable:
            # Drain all queued resize notifications before returning so that
            # rapid consecutive resizes only trigger one redraw.
            try:
                while os.read(resize_fd, 64):
                    pass
            except BlockingIOError:
                pass
            return KEY_RESIZE

        # stdin is ready — delegate to normal key reading.
        return read_key(stream)
