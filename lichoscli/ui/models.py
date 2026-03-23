# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Union

CellStyle = Literal["accent", "danger", "default", "error", "info", "muted", "success", "warning"]
ColumnJustify = Literal["left", "center", "right"]


@dataclass(frozen=True)
class Cell:
    """A table cell with optional semantic styling."""

    text: str
    style: Optional[CellStyle] = None


@dataclass(frozen=True)
class Choice:
    """A selectable prompt choice."""

    value: str
    label: str


@dataclass
class _ColumnDef:
    header: str
    style: Optional[CellStyle] = None
    justify: ColumnJustify = "left"
    no_wrap: bool = False


TableValue = Union[str, Cell]


@dataclass
class TreeNode:
    """A node in a rendered tree structure."""

    label: str
    style: Optional[CellStyle] = None
    children: list["TreeNode"] = field(default_factory=list)


class Tree:
    """Structured tree consumed by output backends."""

    def __init__(self, title: Optional[str] = None) -> None:
        self.title = title
        self._roots: list[TreeNode] = []

    def add_root(self, node: TreeNode) -> "Tree":
        self._roots.append(node)
        return self

    @property
    def roots(self) -> list[TreeNode]:
        return self._roots


class Table:
    """Fluent table builder consumed by output backends."""

    def __init__(self, title: Optional[str] = None) -> None:
        self.title = title
        self._columns: list[_ColumnDef] = []
        self._rows: list[list[TableValue]] = []

    def add_column(
        self,
        header: str,
        *,
        no_wrap: bool = False,
        style: Optional[CellStyle] = None,
        justify: ColumnJustify = "left",
    ) -> "Table":
        self._columns.append(_ColumnDef(header=header, style=style, justify=justify, no_wrap=no_wrap))
        return self

    def add_row(self, *cells: TableValue) -> "Table":
        self._rows.append(list(cells))
        return self

    @property
    def columns(self) -> list[_ColumnDef]:
        return self._columns

    @property
    def rows(self) -> list[list[TableValue]]:
        return self._rows