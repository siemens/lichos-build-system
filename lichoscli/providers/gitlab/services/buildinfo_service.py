# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of BuildInfo service with optimal caching."""

import glob
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Optional

from gitlab import GitlabError

from lichoscli.core.models import BuildInfo, Project
from lichoscli.core.services import BuildInfoResult, BuildInfoService, CacheService
from lichoscli.utils.buildinfo_parser import BuildinfoParser
from lichoscli.utils.build import BuildUtils
from lichoscli.utils.constants import CORE_PACKAGES

if TYPE_CHECKING:
    from lichoscli.core.models import Pipeline

logger = logging.getLogger(__name__)


class GitLabBuildInfoService(BuildInfoService):
    """GitLab-specific implementation of build information service with caching."""

    def __init__(self, gitlab, cache_service: Optional[CacheService] = None):
        """
        Initialize the GitLab buildinfo service.

        Args:
            gitlab: GitLab client instance
            cache_service: Optional cache service for performance optimization
        """
        self.gitlab = gitlab
        self.cache_service = cache_service
        self._buildinfo_cache: dict[str, Optional[BuildInfo]] = {}

    def _extract_buildinfo_from_pipeline(
        self, project: Project, pipeline: "Pipeline", cache_key: str, architecture: str
    ) -> Optional[BuildInfo]:

        if not pipeline:
            return None

        publish_job = pipeline.jobs.get_by_name("publish")

        if not publish_job:
            logger.debug("No publish job found in pipeline for package %s", project.name)
            return None

        try:
            temp_dir = publish_job.artifacts.download_as_directory()
        except GitlabError as e:
            logger.debug(
                "GitLab error downloading artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None

        if not temp_dir:
            logger.debug("No artifacts found for publish job in package %s", project.name)
            return None

        try:
            buildinfo_content = self._find_buildinfo_in_artifacts(temp_dir.name, architecture)

            if not buildinfo_content:
                logger.debug(
                    "No buildinfo file found in artifacts for package %s (architecture: %s)",
                    project.name,
                    architecture,
                )
                return None

            buildinfo = BuildinfoParser.parse(buildinfo_content)
            if buildinfo:
                # Cache the result
                self._buildinfo_cache[cache_key] = buildinfo
                if self.cache_service:
                    self.cache_service.set(cache_key, buildinfo)
                    logger.debug("Cached buildinfo for %s", cache_key)
                return buildinfo

            logger.warning("Failed to parse buildinfo for package %s", project.name)
            return None

        except OSError as e:
            logger.error(
                "File system error processing artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None
        finally:
            temp_dir.cleanup()

    def get_buildinfo(
        self,
        project: Project,
        branch: str | None = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> Optional[BuildInfo]:
        """
        Get buildinfo for a single project with persistent caching.
        CORE_PACKAGES (00ci, build-image) are skipped as they don't have buildinfo files.

        Args:
            project: The project to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch
            wait_for_completion: Whether to wait for pipeline completion. For workspace
                               creation, this can be False to use get_some_latest_pipeline.
            architecture: The architecture to get buildinfo for. If None, uses host architecture.

        Returns:
            BuildInfo if available, None otherwise
        """
        if not self._should_fetch_buildinfo(project):
            return None

        if architecture is None:
            architecture = BuildUtils.normalize_architecture(os.uname().machine)
        else:
            architecture = BuildUtils.normalize_architecture(architecture)

        branch_name = branch if branch else project.default_branch

        if wait_for_completion:
            bi_result = self.get_buildinfo_with_timeout(project, branch_name, architecture=architecture)
            buildinfo = bi_result.buildinfo
        else:
            buildinfo = self._fetch_buildinfo_with_fallback(project, branch_name, architecture)

        return buildinfo

    def get_buildinfo_bulk(
        self,
        projects: list[Project],
        branch: str | None = None,
        wait_for_completion: bool = True,
        architecture: str | None = None,
    ) -> dict[int, BuildInfoResult]:
        """Fetch buildinfo for multiple projects in parallel and return a mapping from project ID to BuildInfoResult."""
        if not projects:
            return {}

        if architecture is None:
            architecture = BuildUtils.normalize_architecture(os.uname().machine)
        else:
            architecture = BuildUtils.normalize_architecture(architecture)

        result: dict[int, BuildInfoResult] = {}
        projects_to_fetch = []

        for project in projects:
            if not self._should_fetch_buildinfo(project):
                result[project.id] = BuildInfoResult()
                continue

            projects_to_fetch.append(project)

        if not projects_to_fetch:
            return result

        def fetch_buildinfo_for_project(
            project: Project,
        ) -> tuple[int, BuildInfoResult]:
            """Fetch buildinfo for a single project and return project ID and result."""
            try:
                branch_name = branch if branch else project.default_branch
                if wait_for_completion:
                    bi_result = self.get_buildinfo_with_timeout(project, branch_name, architecture=architecture)
                else:
                    buildinfo = self._fetch_buildinfo_with_fallback(project, branch_name, architecture)
                    bi_result = BuildInfoResult(buildinfo=buildinfo)
                logger.debug("Successfully fetched buildinfo for project: %s", project.name)
                return project.id, bi_result
            except (GitlabError, OSError) as e:
                logger.warning("Failed to fetch buildinfo for project %s: %s", project.name, str(e))
                return project.id, BuildInfoResult()
            except (AttributeError, ValueError, KeyError) as e:
                logger.error("Data processing error for project %s: %s", project.name, str(e))
                return project.id, BuildInfoResult()

        max_workers = min(8, len(projects_to_fetch))
        logger.info(
            "Fetching buildinfo for %d projects using %d workers",
            len(projects_to_fetch),
            max_workers,
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_project = {
                executor.submit(fetch_buildinfo_for_project, project): project for project in projects_to_fetch
            }

            for future in as_completed(future_to_project):
                project = future_to_project[future]
                try:
                    project_id, bi_result = future.result()
                    result[project_id] = bi_result

                except (
                    GitlabError,
                    OSError,
                    AttributeError,
                    ValueError,
                    KeyError,
                ) as e:
                    logger.error(
                        "Thread execution error for project %s: %s",
                        project.name,
                        str(e),
                    )
                    result[project.id] = BuildInfoResult()

        logger.info("Completed fetching buildinfo for %d projects", len(projects_to_fetch))
        return result

    def get_buildinfo_with_timeout(
        self,
        project: Project,
        branch: str | None = None,
        max_wait_minutes: int = 60,
        architecture: str | None = None,
    ) -> BuildInfoResult:
        if not self._should_fetch_buildinfo(project):
            return BuildInfoResult()

        if architecture is None:
            architecture = BuildUtils.normalize_architecture(os.uname().machine)
        else:
            architecture = BuildUtils.normalize_architecture(architecture)

        branch_name = branch if branch else project.default_branch

        try:
            pipeline = project.pipelines.get_latest(branch_name)
        except GitlabError as e:
            logger.error(
                "GitLab error fetching pipeline for package %s on branch %s: %s",
                project.name,
                branch_name,
                str(e),
            )
            return BuildInfoResult()

        if not pipeline:
            logger.debug(
                "No pipeline found for package %s on branch %s",
                project.name,
                branch_name,
            )
            pipeline = project.pipelines.get_some_latest_pipeline(branch)
            if not pipeline:
                return BuildInfoResult()

        if pipeline.status.is_final:
            if pipeline.status.is_successful:
                logger.debug(
                    "Found successful pipeline %s for %s",
                    pipeline.id,
                    project.name,
                )
            else:
                logger.warning(
                    "Latest pipeline %s for %s failed with status: %s. Looking for previous successful pipeline.",
                    pipeline.id,
                    project.name,
                    pipeline.status.to_string(),
                )
                pipeline = project.pipelines.get_some_latest_pipeline(branch_name)
                if not pipeline:
                    logger.warning(
                        "No successful pipeline found for package %s on branch %s",
                        project.name,
                        branch_name,
                    )
                    return BuildInfoResult()
        elif pipeline.status.is_waiting or pipeline.status.is_active:
            logger.info(
                "Pipeline %s for project %s is %s, waiting for completion...",
                pipeline.id,
                project.name,
                pipeline.status.to_string(),
            )
            max_wait_seconds = max_wait_minutes * 60
            pipeline = self._wait_for_pipeline_completion(project, pipeline, branch_name, max_wait_seconds)
            if not pipeline:
                return BuildInfoResult()
        else:
            logger.warning(
                "Pipeline %s for %s has unexpected status: %s",
                pipeline.id,
                project.name,
                pipeline.status.to_string(),
            )

        cache_key = self._create_cache_key(project, pipeline, architecture)
        cached_buildinfo = self._get_cached_buildinfo(cache_key)
        if cached_buildinfo is not None:
            return BuildInfoResult(buildinfo=cached_buildinfo, pipeline=pipeline)
        # No cache hit, extract from pipeline
        buildinfo = self._extract_buildinfo_from_pipeline(project, pipeline, cache_key, architecture)
        return BuildInfoResult(buildinfo=buildinfo, pipeline=pipeline)

    def clear_cache(self) -> None:
        """Clear both in-memory and persistent cache."""
        self._buildinfo_cache.clear()
        if self.cache_service:
            self.cache_service.clear()
        logger.debug("Cleared buildinfo cache")

    def _get_cached_buildinfo(self, cache_key: str) -> Optional[BuildInfo]:
        """
        Get buildinfo from cache using two-level caching strategy.

        This method first checks the persistent cache service, then falls back
        to the in-memory cache. When a persistent cache hit occurs, it populates
        the in-memory cache for faster subsequent access.

        Args:
            cache_key: The cache key to look up

        Returns:
            BuildInfo if found in cache, None otherwise
        """
        if self.cache_service:
            cached_buildinfo = self.cache_service.get(cache_key)
            if cached_buildinfo is not None:
                logger.debug("Cache hit for buildinfo %s", cache_key)
                self._buildinfo_cache[cache_key] = cached_buildinfo
                return cached_buildinfo

        if cache_key in self._buildinfo_cache:
            return self._buildinfo_cache[cache_key]

        logger.debug("Cache miss for buildinfo %s", cache_key)
        return None


    def _fetch_buildinfo_with_fallback(
        self, project: Project, branch_name: str | None = None, architecture: str | None = None
    ) -> Optional[BuildInfo]:
        """
        Fetch buildinfo using get_some_latest_pipeline for better reliability.

        This method uses get_some_latest_pipeline which finds the most recent successful
        pipeline without waiting for completion, making it suitable for workspace creation.

        Args:
            project: The project to fetch buildinfo for
            branch_name: The branch to get pipeline from
            architecture: The architecture to get buildinfo for

        Returns:
            BuildInfo if available, None otherwise
        """
        if architecture is None:
            architecture = BuildUtils.normalize_architecture(os.uname().machine)
        else:
            architecture = BuildUtils.normalize_architecture(architecture)

        branch_name = branch_name if branch_name else project.default_branch
        pipeline = None
        try:
            pipeline = project.pipelines.get_some_latest_pipeline(branch_name)
        except (GitlabError, ValueError) as e:
            logger.warning(
                "Failed to get any successful pipeline for %s: %s. Falling back to latest pipeline.",
                project.name,
                str(e),
            )

        if not pipeline:
            logger.debug("No successful pipeline found for package %s", project.name)
            return None

        cache_key = self._create_cache_key(project, pipeline, architecture)
        cached_buildinfo = self._get_cached_buildinfo(cache_key)
        if cached_buildinfo is not None:
            return cached_buildinfo

        buildinfo = self._extract_buildinfo_from_pipeline(project, pipeline, cache_key, architecture)
        if buildinfo:
            logger.debug(
                "Successfully fetched buildinfo for %s using successful pipeline",
                project.name,
            )
        return buildinfo

    def _wait_for_pipeline_completion(
        self,
        project: Project,
        pipeline: "Pipeline",
        target_branch: str,
        max_wait_seconds: int,
    ) -> Optional["Pipeline"]:
        """Wait for a pipeline to complete and return the final result."""
        start_time = time.time()
        poll_interval = 30

        logger.info(
            "Waiting for pipeline of project %s to complete (status: %s)",
            project.name,
            pipeline.status.to_string(),
        )
        while time.time() - start_time < max_wait_seconds:
            time.sleep(poll_interval)

            current_pipeline = project.pipelines.get_latest(target_branch, use_cache=False)
            if not current_pipeline or current_pipeline.id != pipeline.id:
                logger.warning(
                    "Pipeline %s is no longer the latest, there is a new latest pipeline for %s. Switching to latest pipeline.",
                    pipeline.id,
                    project.name,
                )
                if not current_pipeline:
                    return None
                pipeline = current_pipeline
            else:
                pipeline = current_pipeline

            if pipeline.status.is_final:
                elapsed_minutes = (time.time() - start_time) / 60
                logger.info(
                    "Pipeline %s for %s completed after %.1f minutes with status: %s",
                    pipeline.id,
                    project.name,
                    elapsed_minutes,
                    pipeline.status.to_string(),
                )

                if pipeline.status.is_successful:
                    logger.info(
                        "Pipeline for %s completed successfully: %s",
                        project.name,
                        pipeline.status.to_string(),
                    )
                    return pipeline
                logger.warning(
                    "Pipeline for %s failed: %s",
                    project.name,
                    pipeline.status.to_string(),
                )
                logger.warning(
                    "Pipeline %s for %s failed. Looking for previous successful pipeline.",
                    pipeline.id,
                    project.name,
                )
                return project.pipelines.get_some_latest_pipeline(target_branch)

            logger.debug(
                "Pipeline %s for %s still %s, continuing to wait...",
                pipeline.id,
                project.name,
                pipeline.status.to_string(),
            )

        elapsed_minutes = (time.time() - start_time) / 60
        logger.warning(
            "Timeout waiting for pipeline %s for %s after %.1f minutes. "
            "Pipeline status: %s. Falling back to previous successful pipeline.",
            pipeline.id,
            project.name,
            elapsed_minutes,
            pipeline.status.to_string(),
        )
        console.print(
            f"Timeout waiting for pipeline of {project.name} "
            f"(waited {elapsed_minutes:.1f} minutes). Using previous successful pipeline."
        )
        return project.pipelines.get_some_latest_pipeline(target_branch)

    def _find_buildinfo_in_artifacts(self, temp_dir_path: str, architecture: str) -> Optional[str]:
        """Find and read architecture-specific buildinfo file from extracted artifacts.

        Supports two artifact layouts:
        - gbp packages: gbp/*_{architecture}.buildinfo
        - images: image/{architecture}/*.buildinfo
        """
        search_patterns = [
            os.path.join(temp_dir_path, "gbp", f"*_{architecture}.buildinfo"),
            os.path.join(temp_dir_path, "image", architecture, "*.buildinfo"),
        ]

        for pattern in search_patterns:
            buildinfo_files = glob.glob(pattern)
            if not buildinfo_files:
                continue
            try:
                with open(buildinfo_files[0], encoding="utf-8") as f:
                    return f.read()
            except OSError as e:
                logger.error("Failed to read buildinfo file %s: %s", buildinfo_files[0], str(e))

        logger.debug("No .buildinfo files found for architecture %s", architecture)
        return None

    def _should_fetch_buildinfo(self, project: Project) -> bool:
        if project.name in CORE_PACKAGES:
            logger.debug("Skipping buildinfo fetch for required package: %s", project.name)
            return False
        return True

    def _create_cache_key(self, project: Project, pipeline: "Pipeline", architecture: str) -> str:
        return f"buildinfo:{project.id}:{pipeline.id}:{architecture}"
