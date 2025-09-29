"""GitLab Pipelines collection wrapper."""

import logging
from typing import List, Optional

import requests
from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProject

from lichoscli.core.models import Pipeline, Pipelines
from lichoscli.core.models import Project as CoreProject

from .pipeline import GitLabPipeline

logger = logging.getLogger(__name__)


class GitLabPipelines(Pipelines):
    """Wrapper for GitLab Project Pipelines collection."""

    def __init__(self, gitlab_project: GitLabProject, core_project: "CoreProject" = None):
        self._project = gitlab_project
        self._core_project_ref = core_project
        self.id = gitlab_project.id

    # demeters law
    def get_latest(self, branch: str = None) -> Optional[Pipeline]:
        """Get the latest pipeline for a branch."""
        target_branch = branch if branch else self._project.default_branch

        try:
            pipelines = self._project.pipelines.list(
                ref=target_branch, per_page=1, order_by="id", sort="desc", get_all=False
            )
            if pipelines:
                return GitLabPipeline(pipelines[0], self._core_project_ref)
            return None
        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.warning(
                "Failed to get pipeline for %s on branch %s (will retry): %s",
                self._project.name,
                target_branch,
                str(e),
            )
            return None

    def list(self, branch: str = None, **kwargs) -> List[Pipeline]:
        """List pipelines for a branch with optional filters."""
        list_params = {}
        if branch:
            list_params["ref"] = branch
        list_params.update(kwargs)

        try:
            pipelines = self._project.pipelines.list(**list_params)
            return [GitLabPipeline(pipeline, self._core_project_ref) for pipeline in pipelines]
        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.warning(
                "Failed to list pipelines for %s (will retry): %s",
                self._project.name,
                str(e),
            )
            return []

    def trigger_build(self, branch_name: str = None) -> int:
        """Trigger a build for a branch.

        If there's an open merge request for the branch, triggers an MR pipeline.
        Otherwise, triggers a regular branch pipeline.
        """
        try:
            ref = branch_name if branch_name else self._project.default_branch

            # Check if there's an open merge request for this branch
            if self._core_project_ref:
                mrs = self._core_project_ref.merge_requests.list(state="opened", branch_name=ref)

                if mrs:
                    mr = mrs[0]  # Use the first (most recent) MR
                    pipeline_id = mr.create_pipeline()
                    logger.info(
                        "Triggered MR pipeline %s for %s on branch %s (MR #%s)",
                        pipeline_id,
                        self._project.name,
                        ref,
                        mr.iid,
                    )
                    return 0

            # Fallback to regular branch pipeline
            pipeline = self._project.pipelines.create({"ref": ref})
            logger.info(
                "Triggered branch pipeline %s for %s on branch %s",
                pipeline.id,
                self._project.name,
                ref,
            )
            return 0
        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.error(
                "Failed to trigger pipeline for %s on branch %s: %s",
                self._project.name,
                branch_name,
                str(e),
            )
            return 1

    def verify_builds_success(self) -> bool:
        """Verify builds and tests for this project."""
        latest_pipeline = self.get_latest()
        return latest_pipeline.status.is_successful if latest_pipeline else False

    def get_some_latest_pipeline(self, branch: str = None) -> Pipeline:
        """Get the most up-to-date successful pipeline.

        Returns the latest successful pipeline from the project. First tries the specified
        branch, then falls back to any branch if no successful pipeline found on target branch.

        Args:
            branch: Branch name to get pipeline from. If None, uses default branch.

        Returns:
            Pipeline: The latest successful pipeline

        Raises:
            ValueError: If no successful pipelines are found anywhere
        """
        target_branch = branch if branch else self._project.default_branch

        try:
            pipelines = self._project.pipelines.list(
                ref=target_branch,
                per_page=20,
                order_by="id",
                sort="desc",
                get_all=False,
            )

            for pipeline in pipelines:
                if pipeline.status == "success":
                    wrapped_pipeline = GitLabPipeline(pipeline, self._core_project_ref)
                    return wrapped_pipeline
            # No successful pipeline found on target branch, try default branch
            if target_branch != self._project.default_branch:
                pipelines = self._project.pipelines.list(per_page=20, order_by="id", sort="desc", get_all=False)
                for pipeline in pipelines:
                    if pipeline.status == "success":
                        wrapped_pipeline = GitLabPipeline(pipeline, self._core_project_ref)
                        logger.info(
                            "Falling back to successful pipeline %s on branch %s for project %s",
                            wrapped_pipeline.id,
                            wrapped_pipeline.ref,
                            self._project.name,
                        )
                        return wrapped_pipeline
            raise ValueError("No successful pipelines found for project %s" % self._project.name)

        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.error(
                "Failed to get latest successful pipeline for %s: %s",
                self._project.name,
                str(e),
            )
            raise ValueError("Could not retrieve successful pipeline for %s: %s" % (self._project.name, str(e))) from e
