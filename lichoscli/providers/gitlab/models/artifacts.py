# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab artifacts model implementation."""

import logging
import os
import tempfile
import zipfile
from typing import Optional

from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProject

from lichoscli.core.models import Artifacts

logger = logging.getLogger(__name__)


class GitLabArtifacts(Artifacts):
    """GitLab implementation of artifacts operations.

    This class represents artifacts for a specific job and ref,
    so the job context is established at instantiation.
    """

    def __init__(self, project: GitLabProject, job_name: str, ref_name: str, job_id: str = None):
        self._project = project
        self._job_name = job_name
        self._ref_name = ref_name
        self._job_id = job_id

    def download(self) -> Optional[bytes]:
        """Download artifacts for this job as bytes."""
        try:
            return self._project.artifacts.download(job=self._job_name, ref_name=self._ref_name)
        except GitlabError as e:
            logger.debug(
                "Failed to download artifacts for job %s, ref %s: %s",
                self._job_name,
                self._ref_name,
                str(e),
            )
            return None

    def download_as_directory(self) -> Optional[tempfile.TemporaryDirectory]:
        """Download artifacts for this job as a temporary directory."""
        temp_dir_obj = None
        try:
            logger.debug(
                "Attempting to download artifacts for job: %s, ref: %s, project: %s",
                self._job_name,
                self._ref_name,
                self._project.name,
            )

            temp_dir_obj = tempfile.TemporaryDirectory(dir="/tmp")
            temp_dir = temp_dir_obj.name

            downloaded = self._try_download_artifacts()
            if downloaded is None:
                logger.debug(
                    "Failed to download artifacts for job '%s' on ref '%s'",
                    self._job_name,
                    self._ref_name,
                )
                logger.debug(
                    "Please ensure a pipeline exists for ref '%s' in the GitLab project.",
                    self._ref_name,
                )
                logger.debug("Project URL: %s", self._project.web_url)
                return None

            safe_ref_name = self._ref_name.replace("/", "_").replace("\\", "_")
            zipfn = os.path.join(temp_dir, f"{self._job_name}_{safe_ref_name}.zip")

            with open(zipfn, "wb") as f:
                f.write(downloaded)
            logger.debug("Successfully wrote artifact to %s", zipfn)

            if os.path.getsize(zipfn) == 0:
                logger.warning("Downloaded artifact file is empty for job: %s", self._job_name)
                return None

            with zipfile.ZipFile(zipfn, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            os.unlink(zipfn)

            return temp_dir_obj
        except GitlabError as e:
            logger.debug(
                "Error processing artifacts: ref=%s, job=%s - %s",
                self._ref_name,
                self._job_name,
                str(e),
            )
            return None
        finally:
            if temp_dir_obj is not None and "downloaded" not in locals():
                temp_dir_obj.cleanup()

    def exists(self) -> bool:
        """Check if artifacts exist for this job."""
        try:
            # Try to get job ID first
            job_id = self._get_job_id()
            if job_id is not None:
                job = self._project.jobs.get(job_id)
                # Check if job has artifacts by checking if download doesn't fail
                try:
                    result = job.artifacts()
                    return result is not None and len(result) > 0
                except GitlabError:
                    return False
            return False
        except GitlabError:
            return False

    def _try_download_artifacts(self) -> Optional[bytes]:
        """Try different methods to download artifacts."""
        try:
            # Method 1: Try via job ID first
            job_id = self._get_job_id()
            if job_id is not None:
                logger.debug("Job found with ID: %s", job_id)
                downloaded = self._download_by_job_id(job_id)
                if downloaded is not None:
                    return downloaded

            # Method 2: Try via merge request
            logger.debug("Job ID download failed, trying via merge requests")
            downloaded = self._download_by_mr()
            if downloaded is not None:
                return downloaded
            logger.debug("Merge request download failed")
            return None

        except GitlabError as e:
            logger.debug(
                "Error downloading artifacts for job: %s, ref: %s: %s",
                self._job_name,
                self._ref_name,
                str(e),
            )
            return None

    def _download_by_job_id(self, job_id: str) -> Optional[bytes]:
        """Download artifacts by job ID as bytes."""
        try:
            logger.debug("Attempting to download artifacts using job ID: %s", job_id)
            if not (job := self._project.jobs.get(job_id)):
                logger.debug("Job %s not found", job_id)
                return None
            result = job.artifacts()
            if result:
                logger.debug("Downloaded %d bytes using job ID: %s", len(result), job_id)
                return result
            logger.debug("Job %s has no artifacts", job_id)
            return None
        except GitlabError as e:
            logger.debug("Failed to download artifacts using job ID %s: %s", job_id, str(e))
            return None

    def _download_by_mr(self) -> Optional[bytes]:
        """Download artifacts via merge request as bytes."""
        try:
            logger.debug(
                "Searching for merge requests with source branch: %s",
                self._ref_name,
            )
            mrs = self._project.mergerequests.list(branch_name=self._ref_name, state="opened")
            if mrs:
                mr_iid = mrs[0].iid
                logger.debug("Found merge request %s for branch %s", mr_iid, self._ref_name)
                result = self._project.artifacts.download(
                    job=self._job_name, ref_name=f"refs/merge-requests/{mr_iid}/head"
                )
                return result
            logger.debug("No merge requests found for branch: %s", self._ref_name)
            return None
        except GitlabError as e:
            logger.debug(
                "Failed to download artifacts via merge request for job: %s, branch: %s: %s",
                self._job_name,
                self._ref_name,
                str(e),
            )
            return None

    def _get_job_id(self) -> Optional[str]:
        """Get job ID for this job's ref and name."""
        if self._job_id:
            return self._job_id
        try:
            target_branch = self._ref_name if self._ref_name else self._project.default_branch
            pipelines = self._project.pipelines.list(
                ref=target_branch, per_page=1, order_by="id", sort="desc", get_all=False
            )

            if not pipelines:
                logger.debug("No pipeline found for ref: %s", self._ref_name)
                return None

            pipeline = pipelines[0]
            jobs = pipeline.jobs.list(all=True)

            job = next((j for j in jobs if j.name == self._job_name), None)
            if job:
                logger.debug(
                    "Job '%s' found - ID: %s, status: %s",
                    self._job_name,
                    job.id,
                    job.status,
                )
                return str(job.id)

            logger.debug("Job '%s' not found in pipeline", self._job_name)
            return None

        except GitlabError as e:
            logger.debug("Error getting job ID: %s", str(e))
            return None
