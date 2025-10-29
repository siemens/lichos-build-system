"""GitLab implementation of workspace service."""

import logging
import os
from typing import Optional

from gitlab import GitlabError

from lichoscli.core.models.workspace import Workspace
from lichoscli.core.services import PackageService, WorkspaceService
from lichoscli.providers.gitlab.models.workspace import GitLabWorkspace
from lichoscli.utils import GitUtils

logger = logging.getLogger(__name__)


class GitLabWorkspaceService(WorkspaceService):
    """GitLab implementation of branch-based workspace operations."""

    def __init__(self, package_service: PackageService):
        """Initialize GitLab workspace service.

        Args:
            package_service: PackageService for getting project information
        """
        self.package_service = package_service

    def create_workspace(
        self,
        name: str,
        package_names: list[str],
    ) -> Workspace:
        """Create a new workspace by creating branches in specified packages.

        Args:
            name: Branch name to create (workspace name)
            package_names: List of package names to create branches in

        Returns:
            Workspace instance representing the created workspace

        Raises:
            ValueError: If workspace already exists or packages don't exist
        """
        all_package_names = set(package_names)

        created_packages = []
        failed_packages = []

        for pkg_name in all_package_names:
            if self.add_package_to_workspace(name, pkg_name):
                package = self.package_service.get_package(pkg_name)
                if package:
                    created_packages.append(package)
            else:
                failed_packages.append(pkg_name)

        if not created_packages and failed_packages:
            raise ValueError(f"Failed to create workspace '{name}': no branches were created")

        if failed_packages:
            logger.warning("Some packages already had branch '%s': %s", name, failed_packages)

        return GitLabWorkspace(
            name=name,
            packages=created_packages,
        )

    def add_package_to_workspace(self, workspace_name: str, package_name: str) -> bool:
        """Add a package to workspace by creating a branch with workspace name.

        Args:
            workspace_name: Name of the workspace (branch name)
            package_name: Name of the package to add

        Returns:
            True if branch was created, False if already exists
        """
        project = self.package_service.get_package(package_name)
        if not project:
            logger.error("Package '%s' not found", package_name)
            return False

        try:
            existing_branches = project.branches.list(search=workspace_name)
            if any(branch.name == workspace_name for branch in existing_branches):
                logger.debug(
                    "Branch '%s' already exists in package '%s'",
                    workspace_name,
                    package_name,
                )
                return False

            default_branch = project.default_branch

            project.branches.create({"branch": workspace_name, "ref": default_branch})

            logger.info("Created branch '%s' in package '%s'", workspace_name, package_name)
            return True

        except GitlabError as e:
            logger.error(
                "Failed to create branch '%s' in package '%s': %s",
                workspace_name,
                package_name,
                str(e),
            )
            return False

    def remove_package_from_workspace(self, workspace_name: str, package_name: str) -> bool:
        """Remove a package from workspace by deleting the branch.

        Args:
            workspace_name: Name of the workspace (branch name)
            package_name: Name of the package to remove

        Returns:
            True if branch was deleted, False if didn't exist
        """
        project = self.package_service.get_package(package_name)
        if not project:
            logger.error("Package '%s' not found", package_name)
            return False

        try:
            # Try to get the branch
            branch = project.branches.get(workspace_name)
            if not branch:
                logger.debug(
                    "Branch '%s' does not exist in package '%s'",
                    workspace_name,
                    package_name,
                )
                return False

            # Delete the branch
            branch.delete()
            logger.info("Deleted branch '%s' from package '%s'", workspace_name, package_name)
            return True

        except GitlabError as e:
            if "404" in str(e):
                logger.debug(
                    "Branch '%s' does not exist in package '%s'",
                    workspace_name,
                    package_name,
                )
                return False
            logger.error(
                "Failed to delete branch '%s' from package '%s': %s",
                workspace_name,
                package_name,
                str(e),
            )
            return False

    def get_workspace(self, name: str) -> Optional[Workspace]:
        """Get a workspace by checking which packages have branches with that name.

        Args:
            name: Workspace/branch name

        Returns:
            Workspace instance if any packages have that branch, None otherwise
        """
        packages = self._get_packages_in_workspace(name)
        if not packages:
            return None

        created_at = None
        last_modified = None

        for project in packages:
            try:
                branch = project.branches.get(name)
                if branch and hasattr(branch, "commit") and hasattr(branch.commit, "created_at"):
                    branch_created = branch.commit.created_at
                    if not created_at or branch_created < created_at:
                        created_at = branch_created
                    if not last_modified or branch_created > last_modified:
                        last_modified = branch_created
            except GitlabError:
                continue

        return GitLabWorkspace(
            name=name,
            packages=packages,
        )

    def _get_branch_to_packages_mapping(self) -> dict[str, list[str]]:
        """Get mapping of branch names to packages that have those branches.

        Returns:
            Dict mapping branch names to list of package names
        """
        all_packages = self.package_service.get_all_packages()
        branch_to_packages: dict[str, list[str]] = {}

        for project in all_packages:
            try:
                branches = project.branches.list(all=True)
                for branch in branches:
                    branch_name = branch.name
                    # Skip default branches (main, master, etc.)
                    if branch_name in ["main", "master", project.default_branch]:
                        continue

                    if branch_name not in branch_to_packages:
                        branch_to_packages[branch_name] = []
                    branch_to_packages[branch_name].append(project.name)
            except GitlabError as e:
                logger.warning("Failed to get branches for package '%s': %s", project.name, str(e))
                continue

        return branch_to_packages

    def _get_branch_to_packages_objects_mapping(self) -> dict[str, list]:
        """Get mapping of branch names to package objects that have those branches.

        Returns:
            Dict mapping branch names to list of package objects
        """
        all_packages = self.package_service.get_all_packages()
        branch_to_packages: dict[str, list] = {}

        for project in all_packages:
            try:
                branches = project.branches.list(all=True)
                for branch in branches:
                    branch_name = branch.name
                    # Skip default branches (main, master, etc.)
                    if branch_name in ["main", "master", project.default_branch]:
                        continue

                    if branch_name not in branch_to_packages:
                        branch_to_packages[branch_name] = []
                    branch_to_packages[branch_name].append(project)
            except GitlabError as e:
                logger.warning("Failed to get branches for package '%s': %s", project.name, str(e))
                continue

        return branch_to_packages

    def list_workspaces(self) -> list[Workspace]:
        """List all workspaces by finding all unique branch names across packages."""

        branch_to_packages = self._get_branch_to_packages_objects_mapping()

        workspaces = []
        for branch_name, packages in branch_to_packages.items():
            workspace = GitLabWorkspace(
                name=branch_name,
                packages=packages,
            )
            workspaces.append(workspace)

        workspaces.sort(key=lambda w: w.name)
        return workspaces

    def delete_workspace(self, name: str) -> bool:
        """Delete a workspace by removing branches with that name from all packages.

        Args:
            name: Workspace/branch name to delete

        Returns:
            True if any branches were deleted, False if workspace didn't exist
        """
        packages = self._get_packages_in_workspace(name)
        if not packages:
            return False

        deleted_count = 0
        for package in packages:
            if self.remove_package_from_workspace(name, package.name):
                deleted_count += 1

        logger.info("Deleted workspace '%s' from %d packages", name, deleted_count)
        return deleted_count > 0

    def get_current_workspace(self) -> Optional[Workspace]:
        """Get the currently active workspace based on LICHOS_BRANCH environment variable or current git branch."""
        branch_name = os.environ.get("LICHOS_BRANCH")

        if not branch_name:
            try:
                repo_data = GitUtils.parse_repo_data()
                if repo_data:
                    branch_name = repo_data[3]  # branch is the 4th element in the tuple
            except (GitlabError, ValueError, AttributeError) as e:
                logger.debug("Could not determine current git branch: %s", str(e))
                return None

        if not branch_name:
            return None

        return self.get_workspace(branch_name)

    def _get_packages_in_workspace(self, workspace_name: str) -> list:
        """Get list of package objects that have branches with the workspace name.

        Args:
            workspace_name: Name of the workspace (branch name)

        Returns:
            List of package objects that have branches with this name
        """
        packages = []
        all_packages = self.package_service.get_all_packages()

        for project in all_packages:
            try:
                branch = project.branches.get(workspace_name)
                if branch:
                    packages.append(project)
            except GitlabError as e:
                logger.debug("Error checking branches for package '%s': %s", project.name, str(e))
                continue

        return sorted(packages, key=lambda p: p.name)

    def get_workspaces_by_package(self, package_name: str) -> list[Workspace]:
        """Get list of workspaces that contain the specified package.

        Args:
            package_name: Name of the package to search for

        Returns:
            List of Workspace objects that exist in this package
        """
        project = self.package_service.get_package(package_name)
        if not project:
            logger.error("Package '%s' not found", package_name)
            return []

        project_branches = project.branches.list(all=True)
        branch_to_packages = self._get_branch_to_packages_objects_mapping()

        workspaces = []
        for branch in project_branches:
            branch_name = branch.name
            if branch_name in ["main", "master", project.default_branch]:
                continue
            packages = branch_to_packages.get(branch_name, [])
            workspace = GitLabWorkspace(
                name=branch_name,
                packages=packages,
            )
            workspaces.append(workspace)

        return sorted(workspaces, key=lambda w: w.name)
