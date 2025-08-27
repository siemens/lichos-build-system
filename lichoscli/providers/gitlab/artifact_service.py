"""GitLab artifact service implementation."""

import logging
import os
import subprocess
import tempfile
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.services import ArtifactService
from lichoscli.core.models import Project
from lichoscli.providers.gitlab.models import GitLabProjectWrapper

logger = logging.getLogger(__name__)


class GitLabArtifactService(ArtifactService):
    """GitLab implementation of artifact management operations."""

    def __init__(self, gitlab):
        self.gitlab = gitlab

    def get_job_artifacts(
        self, package: Project, branch_name: str, job_name: str
    ) -> Optional[tempfile.TemporaryDirectory]:
        """Get job artifacts using gitlab module.
        Returns a TemporaryDirectory containing the extracted artifacts or None if unsuccessful.
        """
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        temp_dir_obj = None
        try:
            logger.debug(
                "Attempting to download artifacts for job: %s, branch: %s, project: %s",
                job_name,
                branch_name,
                package.name,
            )

            temp_dir_obj = tempfile.TemporaryDirectory(dir="/tmp")
            temp_dir = temp_dir_obj.name
            branch_name = branch_name or gitlab_pkg.default_branch

            downloaded = self.try_download_artifacts(package, branch_name, job_name)
            if downloaded is None:
                logger.error(
                    "Failed to download artifacts for job: %s, branch: %s",
                    job_name,
                    branch_name,
                )
                return None

            safe_branch_name = branch_name.replace("/", "_").replace("\\", "_")
            zipfn = os.path.join(temp_dir, f"{job_name}_{safe_branch_name}.zip")

            with open(zipfn, "wb") as f:
                f.write(downloaded)
            logger.debug("Successfully wrote artifact to %s", zipfn)

            if os.path.getsize(zipfn) == 0:
                logger.error("Downloaded artifact file is empty for job: %s", job_name)
                return None

            subprocess.run(["unzip", "-qq", "-bo", zipfn, "-d", temp_dir], check=True)
            os.unlink(zipfn)

            return temp_dir_obj
        except GitlabError as e:
            logger.error(
                "Error processing artifacts: branch=%s, job=%s - %s",
                branch_name,
                job_name,
                str(e),
            )
            return None
        finally:
            if temp_dir_obj is not None and "downloaded" not in locals():
                temp_dir_obj.cleanup()

    def try_download_artifacts(
        self, package: Project, branch_name: str, job_name: str
    ) -> Optional[bytes]:
        """Try different methods to download artifacts."""
        try:
            # Method 1: Try via job ID first
            job_id = self._get_job_id(package, branch_name, job_name)
            if job_id is not None:
                logger.debug("Job found with ID: %s", job_id)
                downloaded = self.get_artifacts_by_job_id(package, job_id)
                if downloaded is not None:
                    return downloaded
            # Method 2: Try via merge request
            logger.debug("Job ID download failed, trying via merge requests")
            downloaded = self.get_artifacts_by_mr(package, branch_name, job_name)
            if downloaded is not None:
                return downloaded
            logger.debug("Merge request download failed")
            return None

        except GitlabError as e:
            logger.error(
                "Error downloading artifacts for job: %s, branch: %s: %s",
                job_name,
                branch_name,
                str(e),
            )
            return None

    def get_artifacts_by_mr(
        self, package: Project, branch_name: str, job_name: str
    ) -> Optional[bytes]:
        """Get job artifacts using merge request.
        Returns downloaded artifact data or None if unsuccessful.
        """
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        try:
            logger.debug(
                "Searching for merge requests with source branch: %s",
                branch_name,
            )
            # Use the MR service to get merge requests
            from .merge_request_service import GitLabMergeRequestService

            mr_service = GitLabMergeRequestService(self.gitlab)
            mrs = mr_service.get_merge_requests_for_package(
                package, branch_name=branch_name, state="opened"
            )
            if mrs:
                mr_iid = mrs[0].iid
                logger.debug(
                    "Found merge request %s for branch %s", mr_iid, branch_name
                )
                result = gitlab_pkg.artifacts.download(
                    job=job_name, ref_name=f"refs/merge-requests/{mr_iid}/head"
                )
                return result
            logger.debug("No merge requests found for branch: %s", branch_name)
            return None
        except GitlabError as e:
            logger.debug(
                "Failed to download artifacts via merge request for job: %s, branch: %s: %s",
                job_name,
                branch_name,
                str(e),
            )
            return None

    def get_artifacts_by_job_id(self, package: Project, job_id: str) -> Optional[bytes]:
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        gitlab_pkg = package.gitlab_project
        try:
            logger.debug("Attempting to download artifacts using job ID: %s", job_id)
            if not (job := gitlab_pkg.jobs.get(job_id)):
                logger.debug("Job %s not found", job_id)
                return None
            result = job.artifacts()
            logger.debug("Downloaded %d bytes using job ID: %s", len(result), job_id)
            return result
        except GitlabError as e:
            logger.debug(
                "Failed to download artifacts using job ID %s: %s", job_id, str(e)
            )
            return None

    def _get_job_id(
        self, package: Project, branch_name: str, job_name: str
    ) -> Optional[str]:
        # Import here to avoid circular imports
        from .pipeline_service import GitLabPipelineService

        pipeline_service = GitLabPipelineService(self.gitlab)

        try:
            latest_pipeline = pipeline_service.get_latest_pipeline(
                package, branch=branch_name
            )

            if not latest_pipeline:
                logger.debug("No pipeline found for branch: %s", branch_name)
                return None

            gitlab_pipeline = latest_pipeline.gitlab_pipeline
            jobs = gitlab_pipeline.jobs.list(all=True)

            job = next((j for j in jobs if j.name == job_name), None)
            if job:
                logger.debug(
                    "Job '%s' found - ID: %s, status: %s",
                    job_name,
                    job.id,
                    job.status,
                )
                return str(job.id)

            logger.debug("Job '%s' not found in pipeline", job_name)
            return None

        except GitlabError as e:
            logger.debug("Error getting job ID: %s", str(e))
            return None
