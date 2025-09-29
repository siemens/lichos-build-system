"""GitLab implementation of BuildInfo service with optimal caching."""

import glob
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Dict, List, Optional

from gitlab import GitlabError

from lichoscli.core.models import BuildInfo, Project
from lichoscli.core.services import BuildInfoService, CacheService
from lichoscli.utils.buildinfo_parser import BuildinfoParser
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
        self._buildinfo_cache: Dict[str, Optional[BuildInfo]] = {}

    def get_buildinfo(
        self, project: Project, branch: str = None, wait_for_completion: bool = True
    ) -> Optional[BuildInfo]:
        """
        Get buildinfo for a single project with persistent caching.
        CORE_PACKAGES (00ci, build-image) are skipped as they don't have buildinfo files.

        Args:
            project: The project to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch
            wait_for_completion: Whether to wait for pipeline completion. For workspace
                               creation, this can be False to use get_some_latest_pipeline.

        Returns:
            BuildInfo if available, None otherwise
        """
        # Skip CORE_PACKAGES as they don't have buildinfo files
        if project.name in CORE_PACKAGES:
            logger.debug("Skipping buildinfo fetch for required package: %s", project.name)
            return None

        branch_name = branch if branch else project.default_branch

        if wait_for_completion:
            buildinfo = self.get_buildinfo_with_waiting(project, branch_name)
        else:
            buildinfo = self._fetch_buildinfo_with_fallback(project, branch_name)

        return buildinfo

    def get_buildinfo_bulk(
        self,
        projects: List[Project],
        branch: str = None,
        wait_for_completion: bool = True,
    ) -> Dict[int, Optional[BuildInfo]]:
        """
        Get buildinfo for multiple projects efficiently using parallel processing.

        This method maintains the same performance characteristics as the original
        implementation by using ThreadPoolExecutor for parallel artifact downloads.
        CORE_PACKAGES (00ci, build-image) are skipped as they don't have buildinfo files.

        Args:
            projects: List of projects to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch for each project
            wait_for_completion: Whether to wait for pipeline completion. If False, uses latest available pipeline.

        Returns:
            Dictionary mapping project ID to BuildInfo (or None if not available)
        """
        if not projects:
            return {}

        result: Dict[int, Optional[BuildInfo]] = {}
        projects_to_fetch = []

        for project in projects:
            if project.name in CORE_PACKAGES:
                logger.debug("Skipping buildinfo fetch for required package: %s", project.name)
                result[project.id] = None
                continue

            projects_to_fetch.append(project)

        if not projects_to_fetch:
            return result

        def fetch_buildinfo_for_project(
            project: Project,
        ) -> tuple[int, Optional[BuildInfo]]:
            """Fetch buildinfo for a single project and return project ID and result."""
            try:
                branch_name = branch if branch else project.default_branch
                if wait_for_completion:
                    buildinfo = self._fetch_buildinfo_from_artifacts(project, branch_name)
                else:
                    buildinfo = self._fetch_buildinfo_with_fallback(project, branch_name)
                logger.debug("Successfully fetched buildinfo for project: %s", project.name)
                return project.id, buildinfo
            except (GitlabError, OSError, IOError) as e:
                logger.warning("Failed to fetch buildinfo for project %s: %s", project.name, str(e))
                return project.id, None
            except (AttributeError, ValueError, KeyError) as e:
                logger.error("Data processing error for project %s: %s", project.name, str(e))
                return project.id, None

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
                    project_id, buildinfo = future.result()
                    result[project_id] = buildinfo

                except (
                    GitlabError,
                    OSError,
                    IOError,
                    AttributeError,
                    ValueError,
                    KeyError,
                ) as e:
                    logger.error(
                        "Thread execution error for project %s: %s",
                        project.name,
                        str(e),
                    )
                    result[project.id] = None

        logger.info("Completed fetching buildinfo for %d projects", len(projects_to_fetch))
        return result

    def clear_cache(self) -> None:
        """Clear both in-memory and persistent cache."""
        self._buildinfo_cache.clear()
        if self.cache_service:
            self.cache_service.clear()
        logger.debug("Cleared buildinfo cache")

    def refresh_buildinfo(self, project: Project) -> Optional[BuildInfo]:
        """
        Force refresh buildinfo for a project, bypassing cache.

        This method clears all cached buildinfo for the project and fetches fresh data.
        Since cache keys now use pipeline IDs, we need to clear any cached entries
        for this project.

        Args:
            project: The project to refresh buildinfo for

        Returns:
            BuildInfo if available, None otherwise
        """
        # Clear any cached buildinfo entries for this project
        # Since we use pipeline ID in cache keys, we need to clear entries that start with project ID
        project_cache_prefix = f"buildinfo:{project.id}:"

        # Clear in-memory cache entries for this project
        keys_to_remove = [key for key in self._buildinfo_cache.keys() if key.startswith(project_cache_prefix)]
        for key in keys_to_remove:
            del self._buildinfo_cache[key]

        # Clear persistent cache entries for this project
        if self.cache_service:
            # Since pattern deletion isn't supported, clear known pipeline cache entries
            # by getting recent pipelines and clearing their cache keys
            try:
                recent_pipelines = project.pipelines.get_latest_pipelines(limit=10)
                for pipeline in recent_pipelines:
                    cache_key = f"buildinfo:{project.id}:{pipeline.id}"
                    self.cache_service.delete(cache_key)
                logger.debug("Cleared persistent cache entries for project %s", project.name)
            except RuntimeError as e:
                logger.warning(
                    "Failed to clear persistent cache for project %s: %s",
                    project.name,
                    str(e),
                )
            logger.debug("Cleared in-memory cache entries for project %s", project.name)

        # Fetch fresh buildinfo - this will cache with the current pipeline ID
        buildinfo = self._fetch_buildinfo_from_artifacts(project, project.default_branch)

        return buildinfo

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

    def _get_fallback_pipeline(self, project: Project, branch: str) -> Optional["Pipeline"]:
        """Get a fallback successful pipeline."""
        try:
            return project.pipelines.get_some_latest_pipeline(branch)
        except (GitlabError, ValueError) as e:
            logger.error(
                "Failed to get fallback pipeline for %s: %s",
                project.name,
                str(e),
            )
            return None

    def _fetch_buildinfo_with_fallback(self, project: Project, branch_name: str = None) -> Optional[BuildInfo]:
        """
        Fetch buildinfo using get_some_latest_pipeline for better reliability.

        This method uses get_some_latest_pipeline which finds the most recent successful
        pipeline without waiting for completion, making it suitable for workspace creation.

        Args:
            project: The project to fetch buildinfo for
            branch_name: The branch to get pipeline from

        Returns:
            BuildInfo if available, None otherwise
        """
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
            # Fallback to the simple non-waiting fetch
            return self._fetch_buildinfo_from_artifacts(project, branch_name)

        if not pipeline:
            logger.debug("No successful pipeline found for package %s", project.name)
            return None

        cache_key = f"buildinfo:{project.id}:{pipeline.id}"

        cached_buildinfo = self._get_cached_buildinfo(cache_key)
        if cached_buildinfo is not None:
            return cached_buildinfo

        publish_job = pipeline.jobs.get_by_name("publish")
        if not publish_job:
            logger.debug("No publish job found in pipeline for package %s", project.name)
            return None

        try:
            temp_dir = publish_job.artifacts.download_as_directory()
        except GitlabError as e:
            logger.error(
                "GitLab error downloading artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None

        if not temp_dir:
            logger.debug("No artifacts found for publish job in package %s", project.name)
            return None

        try:
            buildinfo_content = self._find_buildinfo_in_artifacts(temp_dir.name)

            if not buildinfo_content:
                logger.debug(
                    "No buildinfo file found in artifacts for package %s",
                    project.name,
                )
                return None

            buildinfo = BuildinfoParser.parse(buildinfo_content)
            if buildinfo:
                # Cache the result
                self._buildinfo_cache[cache_key] = buildinfo
                if self.cache_service:
                    self.cache_service.set(cache_key, buildinfo)
                    logger.debug("Cached buildinfo for %s", cache_key)
                logger.debug(
                    "Successfully fetched buildinfo for %s using successful pipeline",
                    project.name,
                )
                return buildinfo

            logger.warning("Failed to parse buildinfo for package %s", project.name)
            return None

        except (OSError, IOError) as e:
            logger.error(
                "File system error processing artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None
        finally:
            temp_dir.cleanup()

    def _wait_for_pipeline_completion(
        self,
        project: Project,
        pipeline: "Pipeline",
        target_branch: str,
        max_wait_seconds: int,
    ) -> Optional["Pipeline"]:
        """Wait for a pipeline to complete and return the final result."""
        from rich.console import Console

        console = Console()
        start_time = time.time()
        poll_interval = 30

        with console.status(
            f"Waiting for pipeline of project {project.name} to complete " f"(status: {pipeline.status.to_string()})"
        ):
            while time.time() - start_time < max_wait_seconds:
                time.sleep(poll_interval)

                current_pipeline = project.pipelines.get_latest(target_branch)
                if not current_pipeline or current_pipeline.id != pipeline.id:
                    logger.warning(
                        "Pipeline %s disappeared, looking for new latest",
                        pipeline.id,
                    )
                    pipeline = current_pipeline
                    if not pipeline:
                        return None
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
                        console.print(
                            f"Pipeline for {project.name} completed successfully: {pipeline.status.to_string()}"
                        )
                        return pipeline
                    console.print(f"Pipeline for {project.name} failed: {pipeline.status.to_string()}")
                    logger.warning(
                        "Pipeline %s for %s failed. Looking for previous successful pipeline.",
                        pipeline.id,
                        project.name,
                    )
                    return self._get_fallback_pipeline(project, target_branch)

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
        return self._get_fallback_pipeline(project, target_branch)

    def get_buildinfo_with_waiting(
        self, project: Project, branch: str = None, max_wait_minutes: int = 60
    ) -> Optional[BuildInfo]:
        """
        Get buildinfo for a project, waiting for pipeline completion if necessary.
        CORE_PACKAGES (00ci, build-image) are skipped as they don't have buildinfo files.

        This method ensures reproducible builds by waiting for the current pipeline
        to complete instead of falling back to stale data from older pipelines.

        Args:
            project: The project to get buildinfo for
            branch: The branch to get buildinfo for. If None, uses project.default_branch
            max_wait_minutes: Maximum time to wait for pipeline completion (default: 60 minutes)

        Returns:
            BuildInfo if available, None otherwise
        """
        # Skip CORE_PACKAGES as they don't have buildinfo files
        if project.name in CORE_PACKAGES:
            logger.debug("Skipping buildinfo fetch for required package: %s", project.name)
            return None

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
            return None

        if not pipeline:
            logger.debug(
                "No pipeline found for package %s on branch %s",
                project.name,
                branch_name,
            )
            pipeline = self._get_fallback_pipeline(project, branch_name)
            if not pipeline:
                return None

        # Now we have a pipeline, create cache key with pipeline ID
        cache_key = f"buildinfo:{project.id}:{pipeline.id}"

        cached_buildinfo = self._get_cached_buildinfo(cache_key)
        if cached_buildinfo is not None:
            return cached_buildinfo

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
                return None
        else:
            logger.warning(
                "Pipeline %s for %s has unexpected status: %s",
                pipeline.id,
                project.name,
                pipeline.status.to_string(),
            )

        # Now extract buildinfo from the pipeline
        publish_job = pipeline.jobs.get_by_name("publish")
        if not publish_job:
            logger.debug("No publish job found in pipeline for package %s", project.name)
            return None

        try:
            temp_dir = publish_job.artifacts.download_as_directory()
        except GitlabError as e:
            logger.error(
                "GitLab error downloading artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None

        if not temp_dir:
            logger.debug("No artifacts found for publish job in package %s", project.name)
            return None

        try:
            buildinfo_content = self._find_buildinfo_in_artifacts(temp_dir.name)

            if not buildinfo_content:
                logger.debug(
                    "No buildinfo file found in artifacts for package %s",
                    project.name,
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

        except (OSError, IOError) as e:
            logger.error(
                "File system error processing artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None
        finally:
            temp_dir.cleanup()

    def _fetch_buildinfo_from_artifacts(self, project: Project, branch_name: str = None) -> Optional[BuildInfo]:
        """
        Fetch buildinfo for a project from GitLab artifacts.

        This is the simple version that gets the latest pipeline without waiting.
        For waiting behavior, use get_buildinfo_with_waiting() instead.

        Args:
            project: The project to fetch buildinfo for
            branch_name: The branch to get pipeline from

        Returns:
            BuildInfo if available, None otherwise
        """
        branch_name = branch_name if branch_name else project.default_branch

        try:
            pipeline = project.pipelines.get_latest(branch_name)
        except GitlabError as e:
            logger.error(
                "GitLab error fetching pipeline for package %s on branch %s: %s",
                project.name,
                branch_name,
                str(e),
            )
            return None

        if not pipeline:
            logger.debug(
                "No pipeline found for package %s on branch %s",
                project.name,
                branch_name,
            )
            return None

        # Create cache key with pipeline ID
        cache_key = f"buildinfo:{project.id}:{pipeline.id}"

        cached_buildinfo = self._get_cached_buildinfo(cache_key)
        if cached_buildinfo is not None:
            return cached_buildinfo

        publish_job = pipeline.jobs.get_by_name("publish")

        if not publish_job:
            logger.debug("No publish job found in pipeline for package %s", project.name)
            return None

        try:
            temp_dir = publish_job.artifacts.download_as_directory()
        except GitlabError as e:
            logger.error(
                "GitLab error downloading artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None

        if not temp_dir:
            logger.debug("No artifacts found for publish job in package %s", project.name)
            return None

        try:
            buildinfo_content = self._find_buildinfo_in_artifacts(temp_dir.name)
            if not buildinfo_content:
                logger.debug(
                    "No buildinfo file found in artifacts for package %s",
                    project.name,
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

        except (OSError, IOError) as e:
            logger.error(
                "File system error processing artifacts for package %s: %s",
                project.name,
                str(e),
            )
            return None
        finally:
            temp_dir.cleanup()

    def _find_buildinfo_in_artifacts(self, temp_dir_path: str) -> Optional[str]:
        """
        Find and read buildinfo file from extracted artifacts.

        This method replicates the exact logic from the original BuildinfoService.
        """

        build_types = ["gbp", "image"]

        for build_type in build_types:
            build_path = os.path.join(temp_dir_path, build_type)
            if not os.path.exists(build_path):
                logger.debug("No %s/ folder found in artifacts", build_type)
                continue

            buildinfo_pattern = os.path.join(build_path, "*.buildinfo")
            buildinfo_files = glob.glob(buildinfo_pattern)

            if not buildinfo_files:
                logger.debug("No .buildinfo files found in %s/ folder", build_type)
                continue

            buildinfo_file = buildinfo_files[0]
            # Reduce debug verbosity - only log if multiple buildinfo files found
            # logger.debug("Found buildinfo file: %s", buildinfo_file)

            try:
                with open(buildinfo_file, "r", encoding="utf-8") as f:
                    content = f.read()
                return content
            except (OSError, IOError) as e:
                logger.error("Failed to read buildinfo file %s: %s", buildinfo_file, str(e))
                continue

        logger.debug("No .buildinfo files found in any build type folders")
        return None
