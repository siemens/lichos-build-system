# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab package service implementation."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.models import Project, Projects
from lichoscli.core.services import PackageService
from lichoscli.providers.gitlab.models import GitLabProject, GitLabProjects
from lichoscli.utils import CIConfigUtils
from lichoscli.utils.constants import CI_PKG

logger = logging.getLogger(__name__)


class GitLabPackageService(PackageService):
    """GitLab implementation of package management operations."""

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab
        self.group_id = gitlab.groups.get(group_rpath).id
        self._packages_cache: dict[str, GitLabProject] = {}
        self._all_packages_cached: bool = False

    def get_projects(self) -> Projects:
        """Get the projects collection for this service's group."""
        return GitLabProjects(self.group_rpath, self.gitlab)

    def _fetch_all_projects(self) -> list[GitLabProject]:
        """Fetch all projects from GitLab API, excluding archived projects."""
        group = self.gitlab.groups.get(self.group_rpath)
        logger.debug(
            "Fetching ALL active projects for group %s (including subgroups)",
            self.group_rpath,
        )
        projects = group.projects.list(include_subgroups=True, all=True, per_page=100)
        full_projects = []

        # Filter out archived projects before making individual API calls
        active_projects = [
            p for p in projects
            if not (hasattr(p, "archived") and p.archived)
        ]
        skipped = len(projects) - len(active_projects)
        if skipped:
            logger.debug("Skipped %d archived projects from group listing", skipped)

        def fetch_project_details(project):
            """Fetch full details for a single project."""
            try:
                full_project = self.gitlab.projects.get(project.id)
                if hasattr(full_project, "archived") and full_project.archived:
                    logger.debug("Skipping archived project: %s", full_project.name)
                    return None
                return full_project
            except GitlabError as e:
                logger.error("Error getting full details for %s: %s", project.name, str(e))
                return project

        max_workers = min(10, len(active_projects))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_project = {executor.submit(fetch_project_details, project): project for project in active_projects}
            for future in as_completed(future_to_project):
                try:
                    full_project = future.result()
                    if full_project is not None:
                        full_projects.append(full_project)
                except GitlabError as e:
                    project = future_to_project[future]
                    logger.error("Unexpected error fetching project %s: %s", project.name, str(e))
                    # Only add non-archived projects even in error cases
                    if not (hasattr(project, "archived") and project.archived):
                        full_projects.append(project)
        return full_projects

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
                    if hasattr(full_project, "archived") and full_project.archived:
                        logger.debug(
                            "Found package %s but it is archived, skipping",
                            package_name,
                        )
                        continue
                    wrapper = GitLabProject(full_project)
                    self._packages_cache[package_name] = wrapper
                    logger.debug("Cached package: %s", package_name)
                    return wrapper

            logger.debug("Package %s not found or is archived", package_name)
            return None
        except GitlabError as e:
            logger.error("Error fetching package %s: %s", package_name, str(e))
            return None

    def get_all_packages(self, with_cache=True) -> list[Project]:
        """Get all packages, using cache when possible."""
        if with_cache and self._all_packages_cached:
            logger.info("Returning %d packages from complete cache", len(self._packages_cache))
            return list(self._packages_cache.values())

        logger.debug("Populating complete package cache")
        projects = self._fetch_all_projects()

        self._packages_cache.clear()
        for project in projects:
            self._packages_cache[project.name] = GitLabProject(project)

        self._all_packages_cached = True
        logger.info("Cached %d packages (complete)", len(self._packages_cache))
        return list(self._packages_cache.values())

    def get_packages_by_branch(self, branch: str) -> list[Project]:
        """Get all packages that have the specified branch."""
        logger.debug("Getting packages with branch: %s", branch)
        all_packages = self.get_all_packages()
        filtered_packages = []

        for pkg in all_packages:
            try:
                if pkg.has_branch(branch):
                    filtered_packages.append(pkg)
            except GitlabError as e:
                logger.debug("Error checking branches for package '%s': %s", pkg.name, str(e))
                continue

        logger.debug("Found %d packages with branch '%s'", len(filtered_packages), branch)
        return filtered_packages

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

        ci_config_path = CIConfigUtils.get_ci_path(self.group_rpath, ci_typ=package_type)

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
            self.invalidate_cache()
            return GitLabProject(project)
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

        # Update properties through the model interface
        if ci_config_path:
            pkg.ci_config_path = ci_config_path
        if branch:
            pkg.default_branch = branch
        pkg.builds_access_level = access_level

        try:
            pkg.save()
            self.invalidate_cache()
            logger.info("Package %s updated successfully.", package_name)
            return pkg
        except GitlabError as e:
            logger.error("Failed to update package %s: %s", package_name, str(e))
            return None

    def get_package_branch(self, package: Project, branch: str):
        if not isinstance(package, GitLabProject):
            raise ValueError("Package must be a GitLabProject")

        try:
            # Use the underlying GitLab project directly for this specific method
            # as this is a provider-specific implementation detail
            return package._project.branches.get(branch)
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

    def pretty_format_ci_path(self, package: Project) -> str:
        """Format CI configuration path for display."""
        result = package.ci_config_path
        if not package.ci_config_path or package.ci_config_path == ".gitlab-ci.yml":
            result = "local"
        else:
            parsed = CIConfigUtils.parse_ci_config_path(package.ci_config_path)
            if parsed:
                group_matches = parsed.group == self.group_rpath
                parent_match = False
                if not group_matches:
                    p = self.get_package(CI_PKG)
                    if p and p.is_fork and p.parent_project_namespace:
                        if p.parent_project_namespace == parsed.group:
                            group_matches = True
                            parent_match = True
                if parsed and group_matches and parsed.pkg == CI_PKG:
                    result = parsed.name
                    if parent_match:
                        result += "*"
                    if parsed.branch:
                        result += ":" + parsed.branch

        logger.debug("%s: %s -> %s", package.name, package.ci_config_path, result)
        return result

    def get_display_name(self, package: Project) -> str:
        """Get display name for a package with subgroup prefix when applicable.

        Args:
            package: The package project to get display name for

        Returns:
            Display name with subgroup prefix when the package is in a subgroup
        """
        namespace = package.namespace
        if namespace.get("full_path") is not None and namespace.get("full_path") != self.group_rpath:
            return namespace.get("path", "") + "/" + package.name
        return package.name
