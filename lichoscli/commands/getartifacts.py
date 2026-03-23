# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import shutil

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.ui import Choice
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

        if not self.job_name:
            latest_pipeline = pkg.pipelines.get_latest(self.branch)
            if not latest_pipeline:
                logger.error("No pipeline found for branch %s", self.branch)
                return 1
            jobs = latest_pipeline.jobs.list()
            if not jobs:
                logger.warning("No jobs found in pipeline")
                return 1
            selected_names = self.prompts.select_many(
                title="Select jobs",
                text="Select jobs to download artifacts from:",
                choices=[Choice(value=job.name, label=f"{job.name} [{job.status}]") for job in jobs],
            )
            if not selected_names:
                return 0
            failed = 0
            for job_name in selected_names:
                result = self._download_specific_job_artifacts(pkg, artifacts_dir, job_name)
                if result:
                    failed += result
            return failed
        return self._download_specific_job_artifacts(pkg, artifacts_dir)

    def _download_specific_job_artifacts(self, pkg, artifacts_dir, job_name=None):
        """Download artifacts for a specific job."""
        job_name = job_name or self.job_name
        latest_pipeline = pkg.pipelines.get_latest(self.branch)
        if not latest_pipeline:
            logger.error("No pipeline found for branch %s", self.branch)
            return 1

        target_job = latest_pipeline.jobs.get_by_name(job_name)
        if not target_job:
            logger.error("Job %s not found in pipeline", job_name)
            return 1

        tempdir = ProgressUtils.execute_with_progress(
            business_logic=target_job.artifacts.download_as_directory,
            description=f"Downloading artifacts for {job_name}...",
            console=self.console,
            success_message="Artifacts downloaded successfully",
            error_message="Failed to download artifacts",
        )

        if not tempdir:
            logger.error("Failed to download artifacts")
            return 1

        self.move_artifacts_to_directory(artifacts_dir, tempdir)
        return 0

    def move_artifacts_to_directory(self, artifacts_dir, tempdir):
        os.makedirs(artifacts_dir, exist_ok=True)
        for fn in os.listdir(tempdir.name):
            dst = os.path.join(artifacts_dir, fn)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            shutil.move(os.path.join(tempdir.name, fn), dst)

    def clear_artifacts_directory(self, artifacts_dir):
        if os.path.exists(artifacts_dir):
            shutil.rmtree(artifacts_dir)
