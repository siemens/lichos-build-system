import logging
import os
import shutil
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class GetartifactsCommand(Command):
    """download pipeline artifacts"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.job_name = args.job_name
        self.branch = args.branch

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("job_name", nargs="?", help="pipeline job name")

    def execute(self):
        pkg = self.pkg_group_handler.get_package(self.package_name)
        artifacts_dir = "artifacts"

        if self.job_name:

            self.clear_artifacts_directory(artifacts_dir)

            tempdir = self.pkg_group_handler.get_job_artifacts(
                branch_name=self.branch, job_name=self.job_name, package=pkg
            )

            if tempdir:
                self.move_artifacts_to_directory(artifacts_dir, tempdir)
                return 0

        latest_pipline = self.pkg_group_handler.get_latest_pipeline(
            self.package_name, self.branch
        )

        if latest_pipline is None:
            logger.warning("No pipeline found for package %s", self.package_name)
            return 1

        jobs = latest_pipline.jobs.list()
        links = self.generate_links_from_jobs(jobs)

        if links:
            print("Artifacts links:")
            for link in links:
                print(link)

        return 0

    def generate_links_from_jobs(self, jobs):
        links = []
        for job in jobs:
            if "build" in job.name or "create" in job.name:
                links.append(f"{job.name}: {job.web_url}/artifacts/browse")
        if len(links) == 0:
            logger.warning("No artifacts found")
        return links

    def move_artifacts_to_directory(self, artifacts_dir, tempdir):
        os.makedirs(artifacts_dir, exist_ok=True)
        for fn in os.listdir(tempdir.name):
            shutil.move(os.path.join(tempdir.name, fn), os.path.join(artifacts_dir, fn))

    def clear_artifacts_directory(self, artifacts_dir):
        if os.path.exists(artifacts_dir):
            shutil.rmtree(artifacts_dir)
