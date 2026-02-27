# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from datetime import datetime


class TimeUtils:
    """Handle time and date formatting operations"""

    @staticmethod
    def format_time_range(started=None, finished=None):
        if not started:
            return "-"

        started_dt = datetime.fromisoformat(started)

        if finished:
            finished_dt = datetime.fromisoformat(finished)
            duration = int((finished_dt - started_dt).total_seconds())
            return f"{started_dt:%Y-%m-%d %H:%M:%S} - {duration}s"
        return f"{started_dt:%Y-%m-%d %H:%M:%S}"
