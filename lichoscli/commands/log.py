import logging
import sys
import time
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils
from rich.console import Console
from rich.text import Text

logger = logging.getLogger(__name__)


class LogCommand(Command):
    """log file of job"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.jobname = args.jobname
        self.wait = args.wait
        self.branch = args.branch

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("jobname", help="job name")
        sp.add_argument("package", nargs="?", help="package name")
        sp.add_argument("--wait", action="store_true", help="wait for job to start")

    def _wait_for_job_start(self, pkg, job):
        """Wait for job to start with a spinner."""
        if not self.wait or job.status not in ("created", "pending"):
            return job

        sys.stdout.write("Waiting ")
        sys.stdout.flush()

        spinner = "/-\\|"
        i = 0

        while job and job.status in ("created", "pending"):
            time.sleep(3)
            sys.stdout.write(f"\b{spinner[i]}")
            sys.stdout.flush()
            i = (i + 1) % 4

            try:
                job = self.pkg_group_handler.gitlab.projects.get(pkg.id).jobs.get(
                    job.id
                )
            except Exception as e:
                logger.error("\nError refreshing job status: %s", e)
                return None

        sys.stdout.write("\n")
        return job

    def normalize_gitlab_log(self, raw_log: str) -> str:
        # line endings: replace \r (carriage return) with \n
        # This avoids "merged" log lines caused by terminal cursor tricks
        return raw_log.replace("\r\n", "\n").replace("\r", "\n")

    def execute(self):

        pkg = self.pkg_group_handler.get_package(self.package_name)
        if pkg is None:
            logger.error("Package %s not found.", self.package_name)
            return 1

        job = self.pkg_group_handler.get_job_by_name(pkg, self.jobname)
        if job is None:
            return 1

        job = self._wait_for_job_start(pkg, job)
        if job is None:
            logger.error("Job %s did not start.", self.jobname)
            return 1

        log_bytes = (
            self.pkg_group_handler.gitlab.projects.get(pkg.id).jobs.get(job.id).trace()
        )
        log = log_bytes.decode("utf-8", errors="replace")
        log = self.normalize_gitlab_log(log)

        console = Console()
        if not log.strip():
            console.print(Text("No log output available.", style="italic"))
        else:
            text = Text.from_ansi(log)
            console.print(text)

        return 0
