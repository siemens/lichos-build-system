# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""ANSI-powered OutputWriter — zero external dependencies."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from . import _ansi
from ..interfaces import ConsoleLike, OutputWriter, StatusDisplay
from ..models import Cell, Table, Tree, TreeNode

_DEFAULT_TEXT_STYLE = "info"

_STYLE_MAP: dict[str | None, str] = {
    None: "",
    "accent": _ansi.BOLD + _ansi.FG_CYAN,
    "danger": _ansi.FG_YELLOW,
    "default": "",
    "error": _ansi.FG_RED,
    "info": _ansi.FG_CYAN,
    "muted": _ansi.DIM,
    "success": _ansi.FG_GREEN,
    "warning": _ansi.FG_YELLOW,
}


def _effective_style(style: str | None, text: str) -> str | None:
    if style is not None:
        return style
    if not text:
        return None
    return _DEFAULT_TEXT_STYLE


# -- StatusDisplay -----------------------------------------------------------


class _TerminalStatus:
    def __init__(self, stream: TextIO, message: str) -> None:
        self._stream = stream
        self._message = message
        self._started = False

    def __enter__(self) -> _TerminalStatus:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        return None

    def start(self) -> None:
        if self._started:
            return
        self._stream.write(self._message + "\n")
        self._stream.flush()
        self._started = True

    def stop(self) -> None:
        self._started = False

    def update(self, message: str) -> None:
        self._stream.write(message + "\n")
        self._stream.flush()


# -- ConsoleLike -------------------------------------------------------------


class TerminalConsole(ConsoleLike):
    """Minimal console backed by ANSI escapes on a plain stream."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def print(
        self,
        *objects: Any,
        sep: str = " ",
        end: str = "\n",
        **kwargs: Any,
    ) -> None:
        del kwargs
        parts = []
        for obj in objects:
            parts.append(str(obj))
        rendered = sep.join(parts) if parts else ""

        self._stream.write(f"{rendered}{end}")
        self._stream.flush()

    def _print_styled(
        self,
        *objects: Any,
        sep: str = " ",
        end: str = "\n",
        style: str = "info",
    ) -> None:
        rendered = sep.join(str(obj) for obj in objects) if objects else ""

        effective_style = _effective_style(style, rendered)
        codes = _STYLE_MAP.get(effective_style, "")
        if codes:
            rendered = f"{codes}{rendered}{_ansi.RESET}"

        self._stream.write(f"{rendered}{end}")
        self._stream.flush()

    def info(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="info")

    def warning(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="warning")

    def error(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="error")

    def success(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="success")

    def accent(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="accent")

    def muted(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="muted")

    def danger(self, *objects: Any, sep: str = " ", end: str = "\n", **kwargs: Any) -> None:
        del kwargs
        self._print_styled(*objects, sep=sep, end=end, style="warning")

    def print_json(self, *, data: Any, **kwargs: Any) -> None:
        del kwargs
        self._stream.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
        self._stream.flush()

    def status(self, status: str, **kwargs: Any) -> StatusDisplay:
        del kwargs
        return _TerminalStatus(self._stream, status)


# -- OutputWriter ------------------------------------------------------------


class TerminalOutput(OutputWriter):
    """Stdlib + ANSI output backend."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout
        self._console = TerminalConsole(self._stream)

    @property
    def console(self) -> ConsoleLike:
        return self._console

    @staticmethod
    def _cell_text(cell: Any) -> str:
        if isinstance(cell, Cell):
            return cell.text
        return str(cell)

    @staticmethod
    def _cell_style(cell: Any) -> str | None:
        if isinstance(cell, Cell):
            return cell.style
        return None

    @staticmethod
    def _justify(text: str, width: int, justify: str) -> str:
        if justify == "right":
            return text.rjust(width)
        if justify == "center":
            return text.center(width)
        return text.ljust(width)

    def print(
        self,
        message: str = "",
        end: str = "\n",
    ) -> None:
        self._stream.write(f"{message}{end}")
        self._stream.flush()

    def _print_styled(
        self,
        message: str = "",
        style: str = "info",
        end: str = "\n",
    ) -> None:
        rendered = message
        effective_style = _effective_style(style, rendered)
        codes = _STYLE_MAP.get(effective_style, "")
        if codes:
            rendered = f"{codes}{rendered}{_ansi.RESET}"
        self._stream.write(f"{rendered}{end}")
        self._stream.flush()

    def table(self, table: Table) -> None:
        headers = [col.header for col in table.columns]
        rows = [[self._cell_text(c) for c in row] for row in table.rows]

        widths = [len(h) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(cell))

        lines: list[str] = []
        if table.title:
            title = self._cell_text(table.title)
            codes = _STYLE_MAP.get(self._cell_style(table.title), "")
            lines.append("{0}{1}{2}".format(codes, title, _ansi.RESET) if codes else title)

        if headers:
            header_line = "  " + "  ".join(
                self._justify(h, widths[i], table.columns[i].justify)
                for i, h in enumerate(headers)
            )
            sep_line = "  " + "  ".join("-" * w for w in widths)
            lines.extend([header_line, sep_line])

        for row_idx, row in enumerate(rows):
            row_parts: list[str] = []
            for idx, cell_text in enumerate(row):
                justified = self._justify(cell_text, widths[idx], table.columns[idx].justify)
                cell_style = self._cell_style(table.rows[row_idx][idx])
                codes = _STYLE_MAP.get(cell_style, "")
                if codes:
                    justified = "{0}{1}{2}".format(codes, justified, _ansi.RESET)
                row_parts.append(justified)
            lines.append("  " + "  ".join(row_parts))

        if lines:
            self.print("\n".join(lines))

    def tree(self, tree: Tree) -> None:
        if tree.title:
            self._print_styled(tree.title, style="accent")
        for index, root in enumerate(tree.roots):
            self._render_tree_node(root, prefix="", is_last=index == len(tree.roots) - 1)

    def _render_tree_node(self, node: TreeNode, prefix: str, is_last: bool) -> None:
        connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
        line = "{0}{1}{2}".format(prefix, connector, node.label)
        codes = _STYLE_MAP.get(node.style, "")
        if codes:
            line = "{0}{1}{2}".format(codes, line, _ansi.RESET)
        self._stream.write("{0}\n".format(line))
        self._stream.flush()
        child_prefix = prefix + ("    " if is_last else "\u2502   ")
        for child_index, child in enumerate(node.children):
            self._render_tree_node(child, prefix=child_prefix, is_last=child_index == len(node.children) - 1)

    def json(self, data: Any) -> None:
        self.print(json.dumps(data, indent=2, sort_keys=True))
