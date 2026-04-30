# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Result type for the schedule preparation phase."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from lichoscli.core.models.dag import DependencyGraph

if TYPE_CHECKING:
    from lichoscli.core.services.dependency import VersionCheckResult


@dataclass
class ScheduleAnalysis:
    """Result of the schedule preparation phase."""

    dag: DependencyGraph
    packages_needing_rebuild: set[str] = field(default_factory=set)
    version_check_results: list[VersionCheckResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None
