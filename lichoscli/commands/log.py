# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import time

from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class LogCommand(Command):
    """Show log file of job"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.jobname = args.job
        self.wait = args.wait
        self.follow = args.follow
        self.branch = args.branch
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="package name")
        sp.add_argument("job", nargs="?", help="job name")
        sp.add_argument(
            "--wait",
            action="store_true",
            help="wait for job to start and finish before showing log (can be combined with --follow)",
        )
        sp.add_argument(
            "--follow",
            "-f",
            action="store_true",
            help="follow log output in real-time (stream live log as it's generated)",
        )

    def _wait_for_job_transition(self, pkg, job, target_states, message, update_message=True):
        """Wait for job to transition to one of the target states."""
        if job.status in target_states:
            return job

        self.console.print(message.format(job_name=job.name, status=job.status))

        last_status = job.status

        with self.console.status("[bold blue]Waiting for job status change...") as status:
            while job and job.status not in target_states:
                time.sleep(1)
                latest_pipeline = pkg.pipelines.get_latest(self.args.branch)
                if latest_pipeline:
                    job = latest_pipeline.jobs.get_by_id(job.id)
                else:
                    job = None
                if job is None:
                    self.console.print("[red]Job not found.[/red]")
                    return None

                if update_message and job.status != last_status:
                    status.stop()
                    self.console.print(f"[yellow]Job status changed to: {job.status}[/yellow]")
                    last_status = job.status
                    status.start()

        self.console.print(f"[green]Job reached target state with status: {job.status}[/green]")
        return job

    def _wait_for_job_start(self, pkg, job):
        """Wait for job to start."""
        return self._wait_for_job_transition(
            pkg,
            job,
            target_states=("running", "success", "failed", "canceled", "skipped"),
            message="Waiting for job '{job_name}' to start (current status: {status})...",
        )

    def _wait_for_job_completion(self, pkg, job):
        """Wait for job to complete."""
        return self._wait_for_job_transition(
            pkg,
            job,
            target_states=("success", "failed", "canceled", "skipped"),
            message="Job '{job_name}' is {status}, waiting for completion...",
        )

    def _stream_job_log(self, pkg, job):
        """Stream job log in real-time."""
        seen_lines = 0

        self._print_header(job)

        if self._is_job_complete(job.status):
            self._show_static_log(pkg)
            return

        try:
            while not self._is_job_complete(job.status):
                latest_pipeline = pkg.pipelines.get_latest(self.args.branch)
                if latest_pipeline:
                    refreshed_job = latest_pipeline.jobs.get_by_id(job.id)
                else:
                    refreshed_job = None
                if refreshed_job is None:
                    logger.error("Failed to refresh job status, stopping stream")
                    break
                job = refreshed_job

                new_lines = self._get_new_log_lines(job, seen_lines)

                if new_lines:
                    self._display_lines(new_lines)
                    seen_lines += len(new_lines)

                time.sleep(2)

            self._print_footer(job.status)

        except KeyboardInterrupt:
            self._print_interrupted()

    def _is_job_complete(self, status):
        """Check if job has completed."""
        return status in ("success", "failed", "canceled", "skipped")

    def _get_new_log_lines(self, job, seen_lines):
        """Fetch and return new log lines since last check."""
        trace = job.get_trace()

        if not trace:
            return []

        log_text = self._decode_trace(trace)
        log_text = self.normalize_gitlab_log(log_text)
        lines = log_text.split("\n")

        return lines[seen_lines:] if seen_lines < len(lines) else []

    def _decode_trace(self, trace):
        """Decode trace to string."""
        return trace.decode("utf-8", errors="replace") if isinstance(trace, bytes) else trace

    def _display_lines(self, lines):
        """Display lines to console with ANSI support."""
        for line in lines:
            self.console.print(Text.from_ansi(line))

    def _print_header(self, job):
        """Print job streaming header."""
        self.console.print(
            Panel(
                f"[bold cyan]Job:[/bold cyan] {job.name}\n[bold yellow]Status:[/bold yellow] {job.status}",
                title="[bold blue]Log Stream[/bold blue]",
                border_style="blue",
            )
        )

    def _print_footer(self, status):
        """Print job completion footer."""
        status_color = {
            "success": "green",
            "failed": "red",
            "canceled": "yellow",
            "skipped": "dim",
        }.get(status, "white")

        self.console.print(Rule())
        self.console.print(f"[bold {status_color}]Job completed with status: {status}[/bold {status_color}]")

    def _print_interrupted(self):
        """Print interruption message."""
        self.console.print(Rule())
        self.console.print("[bold yellow]Log streaming interrupted by user[/bold yellow]")

    def normalize_gitlab_log(self, raw_log: str) -> str:
        # line endings: replace \r (carriage return) with \n
        # This avoids "merged" log lines caused by terminal cursor tricks
        return raw_log.replace("\r\n", "\n").replace("\r", "\n")

    def _list_available_jobs(self, pkg):
        """List available jobs with log links for the package."""
        latest_pipeline = pkg.pipelines.get_latest(self.branch)

        if latest_pipeline is None:
            logger.warning("No pipeline found for package %s", self.package_name)
            return 1

        jobs = latest_pipeline.jobs.list()
        
        if not jobs:
            logger.warning("No jobs found in pipeline")
            return 1

        self.console.print("[bold]Job log links:[/bold]")
        for job in jobs:
            self.console.print(f"  {job.name}: {job.web_url}")

        return 0

    def execute(self):
        pkg = self.package_service.get_package(self.package_name)
        if pkg is None:
            self.console.print(f"[red]Error: Package {self.package_name} not found.[/red]")
            return 1

        if not self.jobname:
            return self._list_available_jobs(pkg)

        job = pkg.merge_requests.get_job_by_name_from_mr(self.jobname, self.args.branch)
        if job is not None:
            self.console.print(
                f"[green]Found job '{self.jobname}' in merge request pipeline for branch {self.branch or 'default'}[/green]"
            )
        else:
            self.console.print("[dim]No job found in merge request, checking branch pipeline...[/dim]")
            latest_pipeline = pkg.pipelines.get_latest(self.args.branch)
            if latest_pipeline:
                job = latest_pipeline.jobs.get_by_name(self.jobname)
                if job is not None:
                    self.console.print(f"[green]Found job '{self.jobname}' in branch pipeline[/green]")

        if job is None:
            self.console.print(f"[red]Error: Job '{self.jobname}' not found in merge request or branch pipeline[/red]")
            return 1

        if self.wait:
            job = self._wait_for_job_start(pkg, job)
            if job is None:
                self.console.print(f"[red]Error: Job {self.jobname} did not start.[/red]")
                return 1

        # Handle different modes
        if self.follow:
            self._stream_job_log(pkg, job)
        elif self.wait:
            job = self._wait_for_job_completion(pkg, job)
            if job is None:
                self.console.print("[red]Error: Failed to wait for job completion.[/red]")
                return 1

            self._show_static_log(pkg)
        else:
            self._show_static_log(pkg)

        return 0

    def _show_static_log(self, pkg):
        """Show the current static log content."""
        log = pkg.merge_requests.extract_log_from_job_mr(self.jobname, self.branch)

        if log is None:
            latest_pipeline = pkg.pipelines.get_latest(self.args.branch)
            if latest_pipeline:
                log = latest_pipeline.jobs.extract_log_from_job(self.jobname)

        if log is None:
            logger.error("Failed to extract log from job %s", self.jobname)
            return
        log = self.normalize_gitlab_log(log)
        if not log.strip():
            self.console.print(
                Panel(
                    "[italic dim]No log output available.[/italic dim]",
                    title="[bold blue]Job Log[/bold blue]",
                    border_style="dim",
                )
            )
        else:
            text = Text.from_ansi(log)
            self.console.print(text)
