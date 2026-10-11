# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from dataclasses import dataclass
from typing import Optional

from lichoscli.core.models.git.git_repo import GitSubmodule


@dataclass(frozen=True)
class SubmoduleChange:
    """A submodule that was added, removed, or moved to another commit or URL."""
    old: Optional[GitSubmodule]
    new: Optional[GitSubmodule]

    @property
    def path(self) -> str:
        return (self.new or self.old).path

    @property
    def kind(self) -> str:
        if self.old is None:
            return "added"
        if self.new is None:
            return "removed"
        return "updated"
