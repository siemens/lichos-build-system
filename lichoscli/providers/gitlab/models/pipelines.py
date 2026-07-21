# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Pipelines collection wrapper."""

import logging

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
        self._cache: dict[str, Pipeline | None] = {}

    # demeters law
    def get_latest(self, branch: str | None = None, use_cache: bool = True) -> Pipeline | None:
        """Return the most recent pipeline for a branch (or default branch)."""
        target_branch = branch if branch else self._project.default_branch

        if use_cache and target_branch in self._cache:
            logger.debug("Using cached pipeline for %s on branch %s", self._project.name, target_branch)
            return self._cache[target_branch]

        try:
            pipelines = self.list(
                target_branch, per_page=1, get_all=False
            )
            result = pipelines[0] if pipelines else None
            if use_cache:
                self._cache[target_branch] = result
            return result
        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.warning(
                "Failed to get pipeline for %s on branch %s (will retry): %s",
                self._project.name,
                target_branch,
                str(e),
            )
            return None

    def invalidate(self, branch: str | None = None) -> None:
        """Drop cached pipelines so the next lookup re-reads from GitLab."""
        if branch is None:
            self._cache.clear()
        else:
            self._cache.pop(branch, None)

    def list(self, branch: str | None = None, **kwargs) -> list[Pipeline]:
        """List pipelines for a branch with optional filters."""
        list_params = {"order_by": "id", "sort": "desc"}
        
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

    def trigger_build(self, branch_name: str = None, variables: dict[str, str] = None) -> Pipeline | None:
        """Trigger a build for a branch with optional variables.

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
                    if variables:
                        logger.warning(
                            "Variables are not supported for MR pipelines, ignoring: %s",
                            ", ".join(f"{k}={v}" for k, v in variables.items())
                        )
                    gitlab_pipeline = self._project.pipelines.get(pipeline_id)
                    pipeline = GitLabPipeline(gitlab_pipeline, self._core_project_ref)
                    return pipeline

            pipeline_data = {"ref": ref}
            if variables:
                pipeline_data["variables"] = [{"key": k, "value": v} for k, v in variables.items()]
                logger.debug("Creating pipeline with variables: %s", variables)

            # Fallback to regular branch pipeline
            gitlab_pipeline = self._project.pipelines.create(pipeline_data)
            logger.info(
                "Triggered branch pipeline %s for %s on branch %s",
                gitlab_pipeline.id,
                self._project.name,
                ref,
            )
            pipeline = GitLabPipeline(gitlab_pipeline, self._core_project_ref)
            return pipeline
        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.error(
                "Failed to trigger pipeline for %s on branch %s: %s",
                self._project.name,
                branch_name,
                str(e),
            )
            return None

    def verify_builds_success(self) -> bool:
        """Verify builds and tests for this project."""
        latest_pipeline = self.get_latest()
        return latest_pipeline.is_successful() if latest_pipeline else False

    def get_some_latest_pipeline(self, branch: str | None = None) -> Pipeline | None:
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
            pipelines = self.list(
                target_branch,
                per_page=100,
                get_all=False,
            )

            for pipeline in pipelines:
                if pipeline.is_successful():
                    return pipeline
            # No successful pipeline found on target branch, try default branch
            if target_branch != self._project.default_branch and pipelines is not None:
                pipelines = self.list(self._project.default_branch, per_page=100, get_all=False)
                for pipeline in pipelines:
                    if pipeline.is_successful():
                        logger.debug(
                            "Falling back to successful pipeline %s on branch %s for project %s",
                            pipeline.id,
                            pipeline.ref,
                            self._project.name,
                        )
                        return pipeline
            logger.debug("No successful pipelines found for project %s", self._project.name)
            return None

        except (GitlabError, requests.exceptions.RequestException) as e:
            logger.error(
                "Failed to get latest successful pipeline for %s: %s",
                self._project.name,
                str(e),
            )
            raise ValueError(f"Could not retrieve successful pipeline for {self._project.name}: {str(e)}") from e
