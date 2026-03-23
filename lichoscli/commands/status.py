# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from datetime import datetime

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.ui import Cell, Table
from lichoscli.utils import BuildUtils, TimeUtils

logger = logging.getLogger(__name__)


class StatusCommand(Command):
    """Show build status of package"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.package_name = BuildUtils.get_package_name(args.package) if args.package else None
        self.dump = args.dump


    def _status_style(cls, status: str) -> str | None:
        if status in ["success", "passed"]:
            return "success"
        if status in ["failed", "failure", "error"]:
            return "error"
        if status in ["canceled", "canceling"]:
            return "warning"
        if status in [
            "running",
            "pending",
            "created",
            "waiting_for_resource",
            "preparing",
            "scheduled",
            "manual",
        ]:
            return "warning"
        return None

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("--dump", action="store_true", help="dump pipeline data as JSON")

    def execute(self):
        if self.package_name:
            return self.print_package_status()
        return self.print_all_status()

    def print_all_status(self):
        packages = self.package_service.get_packages_by_branch(self.args.branch)

        packages_sorted = sorted(packages, key=lambda p: p.path_with_namespace)

        all_successful = True
        failed_packages = []

        table = Table(title="Package Status")
        table.add_column("Name", no_wrap=True)
        table.add_column("Type")
        table.add_column("Enabled")
        table.add_column("Status")
        table.add_column("Pipeline")

        for package in packages_sorted:
            date = "-"

            pipeline = package.pipelines.get_latest(self.args.branch)
            if pipeline:
                status_display = pipeline.status.to_string()
                if not pipeline.status.is_successful:
                    all_successful = False
                    if pipeline.status.is_failed:
                        failed_packages.append(self.package_service.get_display_name(package))

                if pipeline.updated_at:
                    try:
                        date = "{:%Y-%m-%d %H:%M:%S}".format(datetime.fromisoformat(pipeline.updated_at))
                    except ValueError:
                        date = "(Invalid date: {0})".format(pipeline.updated_at)
            else:
                status_display = "-"
                all_successful = False

            table.add_row(
                self.package_service.get_display_name(package),
                self.package_service.pretty_format_ci_path(package),
                str(package.builds_access_level),
                Cell(status_display, style=self._status_style(status_display)),
                date,
            )

        self.output.table(table)

        if not all_successful:
            return 1

        return 0

    def print_package_status(self):
        package = self.package_service.get_package(self.package_name)
        if not package:
            logger.error("Package '%s' not found", self.package_name)
            return 1

        latest_pipeline = package.pipelines.get_latest(self.args.branch)

        if not latest_pipeline:
            logger.error("No pipeline found for package %s", self.package_name)
            return 1

        if self.dump:
            self.output.json(latest_pipeline.to_dict())
            return 0

        details_table = Table(title="Pipeline Details - {0}".format(self.package_name))
        details_table.add_column("Setting", no_wrap=True)
        details_table.add_column("Value")
        details_table.add_row("sha", latest_pipeline.sha or "-")
        details_table.add_row("ref", latest_pipeline.ref or "-")
        details_table.add_row("status", latest_pipeline.status.to_string() if latest_pipeline else "-")
        details_table.add_row("source", latest_pipeline.source or "-")
        details_table.add_row("web_url", latest_pipeline.web_url or "-")
        if latest_pipeline.user:
            details_table.add_row("user", latest_pipeline.user.username)
        self.output.table(details_table)

        jobs_table = Table(title="Pipeline Jobs")
        jobs_table.add_column("Id", no_wrap=True)
        jobs_table.add_column("Name")
        jobs_table.add_column("Stage")
        jobs_table.add_column("Status")
        jobs_table.add_column("Started")
        for job in latest_pipeline.jobs.list():
            job_status = job.status or "-"
            jobs_table.add_row(
                str(job.id),
                job.name or "-",
                job.stage or "-",
                Cell(job_status, style=self._status_style(job_status)),
                TimeUtils.format_time_range(started=job.started_at, finished=job.finished_at) or "-",
            )
        self.output.table(jobs_table)
        return 0
