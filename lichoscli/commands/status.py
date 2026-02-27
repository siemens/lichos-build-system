# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from datetime import datetime

from rich.json import JSON
from rich.table import Table

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils, TimeUtils

logger = logging.getLogger(__name__)

class StatusCommand(Command):
    """Show build status of package"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.package_name = BuildUtils.get_package_name(args.package) if args.package else None
        self.dump = args.dump
        self.group_rpath = self.package_service.get_projects().path

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("--dump", action="store_true", help="dump pipeline data as JSON")

    def execute(self):
        if self.package_name:
            return self.print_package_status()
        return self.print_all_status()

    def print_all_status(self):
        table = Table(title="Package Status")
        table.add_column("Name", no_wrap=True)
        table.add_column("Type")
        table.add_column("Enabled")
        table.add_column("Status")
        table.add_column("Pipeline")

        packages = self.package_service.get_packages_by_branch(self.args.branch)

        packages_sorted = sorted(packages, key=lambda p: p.path_with_namespace)

        all_successful = True
        failed_packages = []

        for package in packages_sorted:
            date = "-"

            pipeline = package.pipelines.get_latest(self.args.branch)
            if pipeline:
                status_display = pipeline.status.to_display_string()
                if not pipeline.status.is_successful:
                    all_successful = False
                    if pipeline.status.is_failed:
                        failed_packages.append(self.package_service.get_display_name(package))
                
                if pipeline.updated_at:
                    try:
                        date = f"{datetime.fromisoformat(pipeline.updated_at):%Y-%m-%d %H:%M:%S}"
                    except ValueError:
                        date = f"(Invalid date: {pipeline.updated_at})"
            else:
                status_display = "-"
                all_successful = False  

            table.add_row(
                self.package_service.get_display_name(package),
                self.package_service.pretty_format_ci_path(package),
                str(package.builds_access_level),
                status_display,
                date,
            )

        self.console.print(table)
        
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
            # Use the model's built-in JSON serialization
            pipeline_data = latest_pipeline.to_dict()
            self.console.print(JSON.from_data(pipeline_data))
            return 0

        details_table = Table(title=f"Pipeline Details - {self.package_name}")
        details_table.add_column("Setting", no_wrap=True)
        details_table.add_column("Value")

        details_table.add_row("sha", latest_pipeline.sha or "-")
        details_table.add_row("ref", latest_pipeline.ref or "-")
        details_table.add_row("status", latest_pipeline.status.to_string() if latest_pipeline else "-")
        details_table.add_row("source", latest_pipeline.source or "-")
        details_table.add_row("web_url", latest_pipeline.web_url or "-")

        if latest_pipeline.user:
            details_table.add_row("user", latest_pipeline.user.username)

        self.console.print(details_table)

        pipeline_jobs = latest_pipeline.jobs.list()

        jobs_table = Table(title="Pipeline Jobs")
        jobs_table.add_column("Id", no_wrap=True)
        jobs_table.add_column("Name")
        jobs_table.add_column("Stage")
        jobs_table.add_column("Status")
        jobs_table.add_column("Started")

        for job in pipeline_jobs:
            job_status = job.status or "-"
            if job_status == "failed":
                status_display = f"[red]{job_status}[/red]"
            elif job_status == "success":
                status_display = f"[green]{job_status}[/green]"
            elif job_status == "running":
                status_display = f"[yellow]{job_status}[/yellow]"
            else:
                status_display = job_status

            jobs_table.add_row(
                str(job.id),
                job.name or "-",
                job.stage or "-",
                status_display,
                TimeUtils.format_time_range(started=job.started_at, finished=job.finished_at) or "-",
            )

        self.console.print(jobs_table)
        return 0
