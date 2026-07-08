# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Presenter that bridges scheduler progress events to UI output."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lichoscli.ui.interfaces import OutputInterface


class SchedulerOutputListener:
    """Translates scheduler progress events into UI output messages."""

    def __init__(self, output: "OutputInterface"):
        self._output = output

    def on_build_triggered(self, package: str, pipeline_url: str) -> None:
        self._output.success("  Successfully triggered build for {0}".format(package))
        self._output.print("    Pipeline: {0}".format(pipeline_url))

    def on_build_succeeded(self, package: str, pipeline_url: str) -> None:
        self._output.success("  {0} completed successfully".format(package))
        self._output.print("    Pipeline: {0}".format(pipeline_url))

    def on_build_failed(self, package: str, reason: str) -> None:
        self._output.error("  {0} {1}".format(package, reason))

    def on_trigger_failed(self, package: str) -> None:
        self._output.error("  Failed to trigger build for {0}".format(package))

    def on_polling_start(self, packages: list) -> None:
        if len(packages) <= 3:
            packages_text = ", ".join(packages)
        else:
            packages_text = ", ".join(packages[:3]) + "... ({0} total)".format(len(packages))
        self._output.accent("\nMonitoring builds: {0}".format(packages_text))

    def on_waiting_for_pipelines(self, packages: list) -> None:
        if not packages:
            return
        if len(packages) <= 3:
            packages_text = ", ".join(packages)
        else:
            packages_text = ", ".join(packages[:3]) + "... ({0} total)".format(len(packages))
        self._output.accent(
            "\nWaiting for {0} running pipeline(s) to complete: {1}".format(
                len(packages), packages_text,
            )
        )

    def on_polling_update(self, still_building: list) -> None:
        if len(still_building) <= 3:
            names_text = ", ".join(still_building)
        else:
            names_text = ", ".join(still_building[:3]) + "... ({0} total)".format(
                len(still_building)
            )
        self._output.muted(
            "Still waiting for {0} packages: {1}".format(len(still_building), names_text)
        )

    def on_blocked(self, packages: list) -> None:
        # Blocked packages are surfaced in the command's post-execution summary
        # via BuildScheduleResult.blocked_packages — no duplicate output here.
        pass
