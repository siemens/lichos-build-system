# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Interactive terminal widgets inspired by the survey library.

Each widget manages its own draw/redraw loop using ANSI escapes and raw
key reading.  No external dependencies.
"""

from __future__ import annotations

import os
import signal
import sys
from typing import List, Optional, TextIO, Tuple

from . import _ansi
from ._keys import (
    KEY_BACKSPACE,
    KEY_DOWN,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_RESIZE,
    KEY_SPACE,
    KEY_UP,
    raw_mode,
    read_key,
    read_key_or_resize,
)

_HAS_SIGWINCH = hasattr(signal, "SIGWINCH")


def _terminal_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def _fuzzy_score(query: str, text: str) -> int | None:
    """Return a score for how well *query* fuzzy-matches *text*.

    Lower is better.  Returns ``None`` when the query does not match at all.
    The algorithm walks *text* left-to-right and tries to consume each
    character of *query* in order, accumulating a penalty for gaps.
    """
    if not query:
        return 0

    query_lower = query.lower()
    text_lower = text.lower()

    qi = 0  # index into query
    score = 0
    last_match = -1

    for ti, ch in enumerate(text_lower):
        if qi < len(query_lower) and ch == query_lower[qi]:
            gap = ti - last_match - 1
            score += gap * gap  # penalise large gaps
            last_match = ti
            qi += 1

    if qi < len(query_lower):
        return None  # not all query chars matched
    return score


# ---------------------------------------------------------------------------
# Select (single-choice) widget
# ---------------------------------------------------------------------------

_VIEW_MAX = 7  # max visible choices before scrolling


class SelectWidget:
    """Arrow-key driven single-select list with inline fuzzy search.

    Typing printable characters filters the list.  Backspace edits the
    query.  Arrow keys navigate, Enter confirms, Escape cancels.
    Returns the original 0-based index of the chosen option.
    """

    def __init__(
        self,
        options: List[str],
        *,
        view_max: int = _VIEW_MAX,
        focus_mark: str = "> ",
        evade_mark: str = "  ",
        focus_color: str = _ansi.FG_CYAN,
        search_color: str = _ansi.FG_RED,
        stream: TextIO | None = None,
        input_stream: TextIO | None = None,
    ) -> None:
        self._options = list(options)
        self._count = len(self._options)
        self._orig_view_max = view_max  # user-requested cap; preserved for resize
        self._view_max = min(view_max, self._count) if self._count else 0
        self._focus_mark = focus_mark
        self._evade_mark = evade_mark
        self._focus_color = focus_color
        self._search_color = search_color
        self._stream = stream or sys.stderr
        self._input = input_stream or sys.stdin

        # Search state
        self._query = ""
        # _filtered holds (original_index, label) pairs
        self._filtered: List[Tuple[int, str]] = list(enumerate(self._options))
        self._cursor = 0  # index into _filtered
        self._offset = 0  # scroll offset into _filtered

    def _apply_filter(self) -> None:
        """Recompute the filtered list from the current query."""
        if not self._query:
            self._filtered = list(enumerate(self._options))
        else:
            scored = []
            for idx, label in enumerate(self._options):
                s = _fuzzy_score(self._query, label)
                if s is not None:
                    scored.append((s, idx, label))
            scored.sort(key=lambda t: t[0])
            self._filtered = [(idx, label) for _, idx, label in scored]

        # Reset cursor to top of the new filtered view
        self._cursor = 0
        self._offset = 0

    @property
    def _display_count(self) -> int:
        return len(self._filtered)

    @property
    def _effective_view(self) -> int:
        return min(self._view_max, self._display_count) if self._display_count else 0

    def _visible_range(self) -> Tuple[int, int]:
        return self._offset, self._offset + self._effective_view

    def _draw_lines(self) -> int:
        """Number of terminal lines occupied by one draw pass."""
        return self._effective_view + (1 if self._query or self._count > self._view_max else 0)

    def _draw(self, *, initial: bool = False) -> None:
        out = self._stream

        if not initial:
            prev = self._prev_lines
            if prev:
                _write(out, _ansi.move_up(prev))

        drawn = 0

        # Search line (always shown if there's a query, or when many items)
        show_search = bool(self._query) or self._count > self._view_max
        if show_search:
            _write(out, _ansi.clear_line() + _ansi.move_to_column(0))
            if self._query:
                search_text = _ansi.paint(self._query, self._search_color)
                _write(out, f"  filter: {search_text}")
                if self._display_count != self._count:
                    _write(out, _ansi.paint(
                        f"  ({self._display_count}/{self._count})",
                        _ansi.DIM,
                    ))
            else:
                _write(out, _ansi.paint("  type to filter...", _ansi.DIM))
            _write(out, "\n")
            drawn += 1

        # Option lines — truncate labels to one terminal row so that
        # _prev_lines stays accurate (wrapping would undercount rows).
        cols = _terminal_width()
        mark_len = max(len(self._focus_mark), len(self._evade_mark))
        ev = self._effective_view
        start, end = self._visible_range()
        for vi in range(start, end):
            _write(out, _ansi.clear_line() + _ansi.move_to_column(0))
            _, label = self._filtered[vi]
            avail = max(0, cols - mark_len)
            if len(label) > avail:
                label = label[:max(0, avail - 1)] + "\u2026"
            if vi == self._cursor:
                line = _ansi.paint(
                    f"{self._focus_mark}{label}",
                    self._focus_color,
                )
            else:
                line = f"{self._evade_mark}{label}"
            _write(out, line + "\n")
            drawn += 1

        # If the previous draw had more lines, clear leftovers
        prev = getattr(self, "_prev_lines", 0)
        if not initial:
            for _ in range(prev - drawn):
                _write(out, _ansi.clear_line() + "\n")
                drawn += 1
            if drawn > prev:
                pass  # no leftover lines
            elif prev > drawn:
                # move back up to where we should be
                _write(out, _ansi.move_up(prev - drawn))

        self._prev_lines = drawn

    def _move(self, delta: int) -> None:
        dc = self._display_count
        if dc == 0:
            return
        new = self._cursor + delta
        if new < 0 or new >= dc:
            return
        self._cursor = new
        # adjust scroll window
        start, end = self._visible_range()
        if self._cursor < start:
            self._offset = self._cursor
        elif self._cursor >= end:
            self._offset = self._cursor - self._effective_view + 1

    def _recalc_view_max(self) -> None:
        """Recompute *_view_max* from current terminal height and option count."""
        try:
            available = max(2, os.get_terminal_size().lines - 3)
        except OSError:
            available = _VIEW_MAX
        self._view_max = min(self._orig_view_max, self._count, available)
        # Keep _offset in bounds after view size change.
        ev = self._effective_view
        max_offset = max(0, self._display_count - ev)
        self._offset = min(self._offset, max_offset)
        if self._cursor < self._offset:
            self._offset = self._cursor
        elif ev > 0 and self._cursor >= self._offset + ev:
            self._offset = self._cursor - ev + 1

    def run(self) -> Optional[int]:
        """Show the widget and block until the user picks or cancels.

        Returns the 0-based *original* index of the chosen option, or
        ``None`` on Escape.
        """
        if not self._options:
            return None

        self._prev_lines = 0
        out = self._stream

        # --- SIGWINCH resize pipe -------------------------------------------
        r_fd = w_fd = -1
        prev_sigwinch = None
        if _HAS_SIGWINCH:
            r_fd, w_fd = os.pipe()
            os.set_blocking(r_fd, False)

            def _resize_handler(signum: int, frame: object) -> None:
                try:
                    os.write(w_fd, b"\x00")
                except OSError:
                    pass

            prev_sigwinch = signal.signal(signal.SIGWINCH, _resize_handler)
        # -------------------------------------------------------------------

        _write(out, _ansi.hide_cursor())
        try:
            with raw_mode(self._input):
                self._draw(initial=True)
                while True:
                    key = read_key_or_resize(self._input, r_fd)
                    if key == KEY_RESIZE:
                        self._recalc_view_max()
                        if self._prev_lines:
                            _write(out, _ansi.move_up(self._prev_lines))
                        _write(out, _ansi.clear_below())
                        self._prev_lines = 0
                        self._draw(initial=True)
                        continue
                    elif key == KEY_UP:
                        self._move(-1)
                    elif key == KEY_DOWN:
                        self._move(1)
                    elif key == KEY_ENTER:
                        if self._filtered:
                            orig_idx, _ = self._filtered[self._cursor]
                            return orig_idx
                        return None
                    elif key == KEY_ESCAPE:
                        return None
                    elif key == KEY_BACKSPACE:
                        if self._query:
                            self._query = self._query[:-1]
                            self._apply_filter()
                    elif len(key) == 1 and key.isprintable():
                        self._query += key
                        self._apply_filter()
                    else:
                        continue
                    self._draw()
        except (KeyboardInterrupt, EOFError):
            return None
        finally:
            _write(out, _ansi.show_cursor())
            if _HAS_SIGWINCH and prev_sigwinch is not None:
                signal.signal(signal.SIGWINCH, prev_sigwinch)
            if r_fd >= 0:
                os.close(r_fd)
            if w_fd >= 0:
                os.close(w_fd)


# ---------------------------------------------------------------------------
# Checkbox (multi-choice) widget
# ---------------------------------------------------------------------------


class CheckboxWidget:
    """Arrow-key driven multi-select list with Space to toggle and fuzzy search.

    Typing filters the visible options.  Backspace edits the query.
    Space toggles selection on the focused item.  Enter confirms.
    Returns a set of *original* indices, or ``None`` on Escape.
    """

    def __init__(
        self,
        options: List[str],
        *,
        active: Optional[List[int]] = None,
        view_max: int = _VIEW_MAX,
        positive_mark: str = "[X] ",
        negative_mark: str = "[ ] ",
        focus_color: str = _ansi.FG_CYAN,
        search_color: str = _ansi.FG_RED,
        stream: TextIO | None = None,
        input_stream: TextIO | None = None,
    ) -> None:
        self._options = list(options)
        self._count = len(self._options)
        self._orig_view_max = view_max  # user-requested cap; preserved for resize
        self._view_max = min(view_max, self._count) if self._count else 0
        self._selected: set[int] = set(active) if active else set()
        self._positive = positive_mark
        self._negative = negative_mark
        self._focus_color = focus_color
        self._search_color = search_color
        self._stream = stream or sys.stderr
        self._input = input_stream or sys.stdin

        # Search state
        self._query = ""
        self._filtered: List[Tuple[int, str]] = list(enumerate(self._options))
        self._cursor = 0
        self._offset = 0

    def _apply_filter(self) -> None:
        if not self._query:
            self._filtered = list(enumerate(self._options))
        else:
            scored = []
            for idx, label in enumerate(self._options):
                s = _fuzzy_score(self._query, label)
                if s is not None:
                    scored.append((s, idx, label))
            scored.sort(key=lambda t: t[0])
            self._filtered = [(idx, label) for _, idx, label in scored]
        self._cursor = 0
        self._offset = 0

    @property
    def _display_count(self) -> int:
        return len(self._filtered)

    @property
    def _effective_view(self) -> int:
        return min(self._view_max, self._display_count) if self._display_count else 0

    def _visible_range(self) -> Tuple[int, int]:
        return self._offset, self._offset + self._effective_view

    def _draw_lines(self) -> int:
        return self._effective_view + (1 if self._query or self._count > self._view_max else 0)

    def _draw(self, *, initial: bool = False) -> None:
        out = self._stream

        if not initial:
            prev = self._prev_lines
            if prev:
                _write(out, _ansi.move_up(prev))

        drawn = 0

        show_search = bool(self._query) or self._count > self._view_max
        if show_search:
            _write(out, _ansi.clear_line() + _ansi.move_to_column(0))
            if self._query:
                search_text = _ansi.paint(self._query, self._search_color)
                _write(out, f"  filter: {search_text}")
                if self._display_count != self._count:
                    _write(out, _ansi.paint(
                        f"  ({self._display_count}/{self._count})",
                        _ansi.DIM,
                    ))
            else:
                _write(out, _ansi.paint("  type to filter...", _ansi.DIM))
            _write(out, "\n")
            drawn += 1

        # Option lines — truncate labels to one terminal row so that
        # _prev_lines stays accurate (wrapping would undercount rows).
        cols = _terminal_width()
        mark_len = max(len(self._positive), len(self._negative))
        ev = self._effective_view
        start, end = self._visible_range()
        for vi in range(start, end):
            _write(out, _ansi.clear_line() + _ansi.move_to_column(0))
            orig_idx, label = self._filtered[vi]
            avail = max(0, cols - mark_len)
            if len(label) > avail:
                label = label[:max(0, avail - 1)] + "\u2026"
            mark = self._positive if orig_idx in self._selected else self._negative
            text = f"{mark}{label}"
            if vi == self._cursor:
                line = _ansi.paint(text, self._focus_color)
            else:
                line = text
            _write(out, line + "\n")
            drawn += 1

        prev = getattr(self, "_prev_lines", 0)
        if not initial:
            for _ in range(prev - drawn):
                _write(out, _ansi.clear_line() + "\n")
                drawn += 1
            if prev > drawn:
                _write(out, _ansi.move_up(prev - drawn))

        self._prev_lines = drawn

    def _move(self, delta: int) -> None:
        dc = self._display_count
        if dc == 0:
            return
        new = self._cursor + delta
        if new < 0 or new >= dc:
            return
        self._cursor = new
        start, end = self._visible_range()
        if self._cursor < start:
            self._offset = self._cursor
        elif self._cursor >= end:
            self._offset = self._cursor - self._effective_view + 1

    def _toggle(self) -> None:
        if not self._filtered:
            return
        orig_idx, _ = self._filtered[self._cursor]
        if orig_idx in self._selected:
            self._selected.discard(orig_idx)
        else:
            self._selected.add(orig_idx)

    def _recalc_view_max(self) -> None:
        """Recompute *_view_max* from current terminal height and option count."""
        try:
            available = max(2, os.get_terminal_size().lines - 3)
        except OSError:
            available = _VIEW_MAX
        self._view_max = min(self._orig_view_max, self._count, available)
        # Keep _offset in bounds after view size change.
        ev = self._effective_view
        max_offset = max(0, self._display_count - ev)
        self._offset = min(self._offset, max_offset)
        if self._cursor < self._offset:
            self._offset = self._cursor
        elif ev > 0 and self._cursor >= self._offset + ev:
            self._offset = self._cursor - ev + 1

    def run(self) -> Optional[set[int]]:
        """Show the widget and block until the user confirms or cancels.

        Returns a :class:`set` of 0-based *original* selected indices,
        or ``None`` on Escape.
        """
        if not self._options:
            return None

        self._prev_lines = 0
        out = self._stream

        # --- SIGWINCH resize pipe -------------------------------------------
        r_fd = w_fd = -1
        prev_sigwinch = None
        if _HAS_SIGWINCH:
            r_fd, w_fd = os.pipe()
            os.set_blocking(r_fd, False)

            def _resize_handler(signum: int, frame: object) -> None:
                try:
                    os.write(w_fd, b"\x00")
                except OSError:
                    pass

            prev_sigwinch = signal.signal(signal.SIGWINCH, _resize_handler)
        # -------------------------------------------------------------------

        _write(out, _ansi.hide_cursor())
        try:
            with raw_mode(self._input):
                self._draw(initial=True)
                while True:
                    key = read_key_or_resize(self._input, r_fd)
                    if key == KEY_RESIZE:
                        self._recalc_view_max()
                        if self._prev_lines:
                            _write(out, _ansi.move_up(self._prev_lines))
                        _write(out, _ansi.clear_below())
                        self._prev_lines = 0
                        self._draw(initial=True)
                        continue
                    elif key == KEY_UP:
                        self._move(-1)
                    elif key == KEY_DOWN:
                        self._move(1)
                    elif key == KEY_SPACE:
                        self._toggle()
                    elif key == KEY_ENTER:
                        return set(self._selected)
                    elif key == KEY_ESCAPE:
                        return None
                    elif key == KEY_BACKSPACE:
                        if self._query:
                            self._query = self._query[:-1]
                            self._apply_filter()
                    elif len(key) == 1 and key.isprintable():
                        self._query += key
                        self._apply_filter()
                    else:
                        continue
                    self._draw()
        except (KeyboardInterrupt, EOFError):
            return None
        finally:
            _write(out, _ansi.show_cursor())
            if _HAS_SIGWINCH and prev_sigwinch is not None:
                signal.signal(signal.SIGWINCH, prev_sigwinch)
            if r_fd >= 0:
                os.close(r_fd)
            if w_fd >= 0:
                os.close(w_fd)


# ---------------------------------------------------------------------------
# Confirm (yes / no) widget
# ---------------------------------------------------------------------------


class ConfirmWidget:
    """Inline yes/no prompt with single-keypress response.

    Pressing ``y`` or ``n`` immediately returns.  Enter accepts the default.
    Escape returns ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        default: bool = False,
        yes_color: str = _ansi.FG_GREEN,
        no_color: str = _ansi.FG_RED,
        stream: TextIO | None = None,
        input_stream: TextIO | None = None,
    ) -> None:
        self._message = message
        self._default = default
        self._yes_color = yes_color
        self._no_color = no_color
        self._stream = stream or sys.stderr
        self._input = input_stream or sys.stdin

    def run(self) -> Optional[bool]:
        """Show the prompt and return ``True``, ``False``, or ``None``."""
        out = self._stream

        if self._default:
            hint = _ansi.paint("Y", _ansi.BOLD) + "/n"
        else:
            hint = "y/" + _ansi.paint("N", _ansi.BOLD)

        prompt = f"{self._message} [{hint}] "
        _write(out, prompt)

        try:
            with raw_mode(self._input):
                while True:
                    key = read_key(self._input)
                    if key in ("y", "Y"):
                        _write(out, _ansi.paint("Yes", self._yes_color) + "\n")
                        return True
                    if key in ("n", "N"):
                        _write(out, _ansi.paint("No", self._no_color) + "\n")
                        return False
                    if key == KEY_ENTER:
                        answer = "Yes" if self._default else "No"
                        color = self._yes_color if self._default else self._no_color
                        _write(out, _ansi.paint(answer, color) + "\n")
                        return self._default
                    if key == KEY_ESCAPE:
                        _write(out, "\n")
                        return None
        except (KeyboardInterrupt, EOFError):
            _write(out, "\n")
            return None
