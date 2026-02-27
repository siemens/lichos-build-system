# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import shutil

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils, ProgressUtils

logger = logging.getLogger(__name__)


class GetartifactsCommand(Command):
    """Download pipeline artifacts"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.job_name = args.job
        self.branch = args.branch
        self.package_service = di_container.obtain_ref(PackageService)
        self.package_name = BuildUtils.get_package_name(args.package)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("job", nargs="?", help="pipeline job name")

    def execute(self):
        pkg = self.package_service.get_package(self.package_name)

        if pkg is None:
            logger.error("Package '%s' not found", self.package_name)
            return 1

        artifacts_dir = "artifacts"

        if self.job_name:
            return self._download_specific_job_artifacts(pkg, artifacts_dir)
        return self._list_available_artifacts(pkg)

    def _download_specific_job_artifacts(self, pkg, artifacts_dir):
        """Download artifacts for a specific job."""
        self.clear_artifacts_directory(artifacts_dir)

        latest_pipeline = pkg.pipelines.get_latest(self.branch)
        if not latest_pipeline:
            logger.error("No pipeline found for branch %s", self.branch)
            return 1

        target_job = latest_pipeline.jobs.get_by_name(self.job_name)
        if not target_job:
            logger.error("Job %s not found in pipeline", self.job_name)
            return 1

        tempdir = ProgressUtils.execute_with_progress(
            business_logic=target_job.artifacts.download_as_directory,
            description=f"Downloading artifacts for {self.job_name}...",
            console=self.console,
            success_message="Artifacts downloaded successfully",
            error_message="Failed to download artifacts",
        )

        if not tempdir:
            logger.error("Failed to download artifacts")
            return 1

        self.move_artifacts_to_directory(artifacts_dir, tempdir)
        return 0

    def _list_available_artifacts(self, pkg):
        """List available artifacts for the package."""
        latest_pipeline = pkg.pipelines.get_latest(self.branch)

        if latest_pipeline is None:
            logger.warning("No pipeline found for package %s", self.package_name)
            return 1

        jobs = latest_pipeline.jobs.list()
        
        if not jobs:
            logger.warning("No jobs found in pipeline")
            return 1

        self.console.print("[bold]Artifacts links:[/bold]")
        for job in jobs:
            self.console.print(f"  {job.name}: {job.web_url}/artifacts/browse")

        return 0

    def move_artifacts_to_directory(self, artifacts_dir, tempdir):
        os.makedirs(artifacts_dir, exist_ok=True)
        for fn in os.listdir(tempdir.name):
            shutil.move(os.path.join(tempdir.name, fn), os.path.join(artifacts_dir, fn))

    def clear_artifacts_directory(self, artifacts_dir):
        if os.path.exists(artifacts_dir):
            shutil.rmtree(artifacts_dir)
