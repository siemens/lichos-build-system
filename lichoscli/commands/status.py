from datetime import datetime
import json
import logging
from lichoscli import utils
from lichoscli.commands.base import Command
from tabulate import tabulate

logger = logging.getLogger(__name__)


class StatusCommand(Command):
    """build status of package"""

    def __init__(self, pkg_group_handler, args):
        super().__init__(pkg_group_handler, args)
        self.package_name = utils.BuildUtils.get_package_name(args.package)
        self.dump = args.dump

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")

    def execute(self):
        if self.package_name:
            return self.print_package_status()
        else:
            return self.print_all_status()

    def print_all_status(self):
        t = [["Name", "Type", "Enabled", "Status", "Pipeline"]]
        packages = self.pkg_group_handler.get_all_packages()
        pipeline_statuses = self.pkg_group_handler.get_all_pipelines_status(max_workers=10, branch=self.args.branch)

        for package in packages:
            status = "-"
            date = "-"

            pipeline = pipeline_statuses.get(package.name)
            if pipeline:
                status = getattr(pipeline, "status", "-") or "-"

                updated_at = getattr(pipeline, "updated_at", None)
                if updated_at:
                    try:
                        date = f"{datetime.fromisoformat(updated_at):%Y-%m-%d %H:%M:%S}"
                    except ValueError:
                        date = f"(Invalid date: {updated_at})"

            t.append(
                [
                    package.name,
                    self.pkg_group_handler.pretty_format_ci_path(package),
                    package.builds_access_level,
                    status,
                    date,
                ]
            )

        print(tabulate(t, headers="firstrow"))
        return 0

    def print_package_status(self):
        latest_pipeline = self.pkg_group_handler.get_latest_pipeline(self.package_name, self.args.branch)

        if not latest_pipeline:
            logger.error("No pipeline found for package %s", self.package_name)
            return

        if self.dump:
            print(json.dumps(latest_pipeline, indent=2))
            return

        headers = [
            ["Setting", "Value"],
            ["sha", latest_pipeline.sha],
            ["ref", latest_pipeline.ref],
            ["status", latest_pipeline.status],
            ["source", latest_pipeline.source],
            ["web_url", latest_pipeline.web_url],
        ]
        if hasattr(latest_pipeline, "user"):
            headers.append(["user", latest_pipeline.user.username])

        print(tabulate(headers, headers="firstrow"))

        pipeline_jobs = latest_pipeline.jobs.list(all=True)

        print("\nPipeline Jobs:\n")
        job_headers = ["Id", "Name", "Stage", "Status", "Started"]
        job_rows = [
            [
                job.id,
                job.name,
                job.stage,
                job.status,
                utils.TimeUtils.format_time_range(
                    started=job.started_at, finished=job.finished_at
                ),
            ]
            for job in pipeline_jobs
        ]
        print(tabulate(job_rows, headers=job_headers))
        return 0
