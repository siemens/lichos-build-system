"""GitLab package service implementation."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List

from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProject

from lichoscli.core.services import PackageService
from lichoscli.core.models import Project
from lichoscli.providers.gitlab.models import GitLabProjectWrapper
from lichoscli.utils import CIConfigUtils

logger = logging.getLogger(__name__)


class GitLabPackageService(PackageService):
    """GitLab implementation of package management operations."""

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab
        self.group_id = gitlab.groups.get(group_rpath).id
        self._packages_cache: Dict[str, GitLabProjectWrapper] = {}

    def _fetch_all_projects(self) -> List[GitLabProject]:
        """Fetch all projects from GitLab API, excluding archived projects."""
        group = self.gitlab.groups.get(self.group_rpath)
        logger.debug(
            "Fetching ALL active projects for group %s (including subgroups)",
            self.group_rpath,
        )
        projects = group.projects.list(include_subgroups=True, all=True)
        full_projects = []

        def fetch_project_details(project):
            """Fetch full details for a single project."""
            try:
                full_project = self.gitlab.projects.get(project.id)
                # Double-check that the project is not archived
                if hasattr(full_project, "archived") and full_project.archived:
                    logger.debug("Skipping archived project: %s", full_project.name)
                    return None
                logger.debug("Fetched full details for package: %s", full_project.name)
                return full_project
            except GitlabError as e:
                logger.error(
                    "Error getting full details for %s: %s", project.name, str(e)
                )
                return project

        max_workers = min(10, len(projects))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_project = {
                executor.submit(fetch_project_details, project): project
                for project in projects
            }
            for future in as_completed(future_to_project):
                try:
                    full_project = future.result()
                    if (
                        full_project is not None
                    ):  # Skip None results (archived projects)
                        full_projects.append(full_project)
                except GitlabError as e:
                    project = future_to_project[future]
                    logger.error(
                        "Unexpected error fetching project %s: %s", project.name, str(e)
                    )
                    # Only add non-archived projects even in error cases
                    if not (hasattr(project, "archived") and project.archived):
                        full_projects.append(project)
        return full_projects

    def populate_cache(self):
        if self._packages_cache:
            return

        logger.debug("Populating package cache")
        projects = self._fetch_all_projects()

        for project in projects:
            self._packages_cache[project.name] = GitLabProjectWrapper(project)

        logger.debug("Cached %d packages", len(self._packages_cache))

    def get_package(self, package_name: str) -> Optional[Project]:
        if package_name in self._packages_cache:
            logger.debug("Cache hit for package: %s", package_name)
            return self._packages_cache[package_name]

        try:
            logger.debug("Fetching package details for: %s", package_name)
            group = self.gitlab.groups.get(self.group_rpath)
            projects = group.projects.list(search=package_name, include_subgroups=True)

            for project in projects:
                if project.name == package_name:
                    full_project = self.gitlab.projects.get(project.id)
                    # Double-check that the project is not archived
                    if hasattr(full_project, "archived") and full_project.archived:
                        logger.debug(
                            "Found package %s but it is archived, skipping",
                            package_name,
                        )
                        continue
                    wrapper = GitLabProjectWrapper(full_project)
                    self._packages_cache[package_name] = wrapper
                    logger.debug("Cached package: %s", package_name)
                    return wrapper

            logger.debug("Package %s not found or is archived", package_name)
            return None
        except GitlabError as e:
            logger.error("Error fetching package %s: %s", package_name, str(e))
            return None

    def get_all_packages(self) -> List[Project]:
        """Get all packages, using cache when possible."""
        self.populate_cache()
        return list(self._packages_cache.values())

    def create_package(
        self,
        name: str,
        branch: str,
        package_type: str,
        subgroup: str,
        access_level: str = "enabled",
    ) -> Optional[Project]:
        namespace_id = self.get_subgroup_namespace_id(subgroup)
        if namespace_id is None:
            logger.error("Failed to get namespace ID for subgroup: %s", subgroup)
            return None

        ci_config_path = CIConfigUtils.get_ci_path(
            self.group_rpath, ci_typ=package_type
        )

        try:
            project = self.gitlab.projects.create(
                {
                    "name": name,
                    "namespace_id": namespace_id,
                    "ci_config_path": ci_config_path,
                    "default_branch": branch,
                    "builds_access_level": access_level,
                }
            )
            # Invalidate cache since we added new data
            self.invalidate_cache()
            return GitLabProjectWrapper(project)
        except GitlabError as e:
            logger.error("Failed to create package %s: %s", name, str(e))
            return None

    def update_package(
        self,
        package_name: str,
        ci_config_path: Optional[str] = None,
        branch: Optional[str] = None,
        access_level: str = "enabled",
    ) -> Optional[Project]:
        pkg = self.get_package(package_name)

        if not pkg:
            logger.error("Package %s not found.", package_name)
            return None

        gitlab_pkg = pkg.gitlab_project
        if ci_config_path:
            gitlab_pkg.ci_config_path = ci_config_path
        if branch:
            gitlab_pkg.default_branch = branch
        gitlab_pkg.builds_access_level = access_level

        try:
            gitlab_pkg.save()
            self.invalidate_cache()
            logger.info("Package %s updated successfully.", package_name)
            return GitLabProjectWrapper(gitlab_pkg)
        except GitlabError as e:
            logger.error("Failed to update package %s: %s", package_name, str(e))
            return None

    def get_package_branch(self, package: Project, branch: str):
        if not isinstance(package, GitLabProjectWrapper):
            raise ValueError("Package must be a GitLabProjectWrapper")

        try:
            return package.gitlab_project.branches.get(branch)
        except GitlabError as e:
            logger.error(
                "Failed to retrieve branch '%s' for package '%s': %s",
                branch,
                package.name,
                str(e),
            )
            return None

    def get_subgroup_namespace_id(self, subgroup: str) -> Optional[int]:
        """Get namespace ID for a subgroup."""
        if not subgroup:
            return self.group_id

        try:
            subgroup_obj = self.gitlab.groups.get(f"{self.group_rpath}/{subgroup}")
            return subgroup_obj.id
        except GitlabError as e:
            logger.error("Failed to get subgroup %s: %s", subgroup, str(e))
            return None

    def invalidate_cache(self):
        logger.debug("Invalidating package cache")
        self._packages_cache.clear()
