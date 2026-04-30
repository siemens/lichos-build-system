# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Result type for the build execution phase."""

from dataclasses import dataclass, field


@dataclass
class BuildScheduleResult:
    """Result of the build execution phase."""

    total_builds: int = 0
    failed_builds: int = 0
    blocked_packages: list[str] = field(default_factory=list)
