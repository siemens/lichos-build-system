import logging
import time
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils
from rich.console import Console
from rich.text import Text

logger = logging.getLogger(__name__)


class LogCommand(Command):
    """Show log file of job"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.jobname = args.jobname
        self.wait = args.wait
        self.follow = args.follow
        self.branch = args.branch

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("jobname", help="job name")
        sp.add_argument("package", nargs="?", help="package name")
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

    def _wait_for_job_transition(
        self, pkg, job, target_states, message, update_message=True
    ):
        """Wait for job to transition to one of the target states."""
        if job.status in target_states:
            return job

        print(message.format(job_name=job.name, status=job.status))

        last_status = job.status
        spinner = "|/-\\"
        spinner_index = 0

        while job and job.status not in target_states:
            print(f"\r{spinner[spinner_index]} Waiting...", end="", flush=True)
            spinner_index = (spinner_index + 1) % len(spinner)
            time.sleep(1)
            job = self.pkg_group_handler.get_job_by_id(pkg, job.id)
            if job is None:
                print("\nJob not found.")
                return None

            if update_message and job.status != last_status:
                print(f"\nJob status changed to: {job.status}")
                last_status = job.status

        print(f"\nJob reached target state with status: {job.status}")
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
        console = Console()
        seen_lines = 0

        self._print_header(job)

        if self._is_job_complete(job.status):
            self._show_static_log(pkg)
            return

        try:
            while not self._is_job_complete(job.status):
                refreshed_job = self.pkg_group_handler.get_job_by_id(pkg, job.id)
                if refreshed_job is None:
                    logger.error("Failed to refresh job status, stopping stream")
                    break
                job = refreshed_job

                new_lines = self._get_new_log_lines(pkg, job, seen_lines)

                if new_lines:
                    self._display_lines(console, new_lines)
                    seen_lines += len(new_lines)

                time.sleep(2)

            self._print_footer(job.status)

        except KeyboardInterrupt:
            self._print_interrupted()

    def _is_job_complete(self, status):
        """Check if job has completed."""
        return status in ("success", "failed", "canceled", "skipped")

    def _get_new_log_lines(self, pkg, job, seen_lines):
        """Fetch and return new log lines since last check."""
        full_job = pkg.jobs.get(job.id)
        trace = full_job.trace()

        if not trace:
            return []

        log_text = self._decode_trace(trace)
        log_text = self.normalize_gitlab_log(log_text)
        lines = log_text.split("\n")

        return lines[seen_lines:] if seen_lines < len(lines) else []

    def _decode_trace(self, trace):
        """Decode trace to string."""
        return (
            trace.decode("utf-8", errors="replace")
            if isinstance(trace, bytes)
            else trace
        )

    def _display_lines(self, console, lines):
        """Display lines to console with ANSI support."""
        for line in lines:
            console.print(Text.from_ansi(line))

    def _print_header(self, job):
        """Print job streaming header."""
        print(f"Streaming log for job '{job.name}' (status: {job.status})")
        print("=" * 50)

    def _print_footer(self, status):
        """Print job completion footer."""
        print("=" * 50)
        print(f"Job completed with status: {status}")

    def _print_interrupted(self):
        """Print interruption message."""
        print("\n" + "=" * 50)
        print("Log streaming interrupted by user")

    def normalize_gitlab_log(self, raw_log: str) -> str:
        # line endings: replace \r (carriage return) with \n
        # This avoids "merged" log lines caused by terminal cursor tricks
        return raw_log.replace("\r\n", "\n").replace("\r", "\n")

    def execute(self):
        pkg = self.pkg_group_handler.get_package(self.package_name)
        if pkg is None:
            logger.error("Package %s not found.", self.package_name)
            return 1

        job = self.pkg_group_handler.get_job_by_name_from_mr(
            pkg, self.jobname, self.args.branch
        )
        if job is not None:
            logger.info(
                "Found job '%s' in merge request pipeline for branch %s",
                self.jobname,
                self.branch or "default",
            )
        else:
            logger.debug("No job found in merge request, checking branch pipeline")
            job = self.pkg_group_handler.get_job_by_name(pkg, self.jobname)
            if job is not None:
                logger.info("Found job '%s' in branch pipeline", self.jobname)

        if job is None:
            logger.error(
                "Job '%s' not found in merge request or branch pipeline", self.jobname
            )
            return 1

        if self.wait:
            job = self._wait_for_job_start(pkg, job)
            if job is None:
                logger.error("Job %s did not start.", self.jobname)
                return 1

        # Handle different modes
        if self.follow:
            # Stream live log (regardless of wait flag)
            self._stream_job_log(pkg, job)
        elif self.wait:
            # Wait for completion then show full log (only if not following)
            job = self._wait_for_job_completion(pkg, job)
            if job is None:
                logger.error("Failed to wait for job completion.")
                return 1

            self._show_static_log(pkg)
        else:
            self._show_static_log(pkg)

        return 0

    def _show_static_log(self, pkg):
        """Show the current static log content."""
        log = self.pkg_group_handler.extract_log_from_job_mr(
            pkg, self.jobname, self.branch
        )

        if log is None:
            log = self.pkg_group_handler.extract_log_from_job(pkg, self.jobname)

        if log is None:
            logger.error("Failed to extract log from job %s", self.jobname)
            return
        log = self.normalize_gitlab_log(log)
        console = Console()
        if not log.strip():
            console.print(Text("No log output available.", style="italic"))
        else:
            text = Text.from_ansi(log)
            console.print(text)
