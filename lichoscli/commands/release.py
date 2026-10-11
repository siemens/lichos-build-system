#!/usr/bin/python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

import requests

from lichoscli.commands.base import Command
from lichoscli.core.exceptions import BranchError, ProviderAPIError, ValidationError
from lichoscli.core.di import DIContainer
from lichoscli.core.models.git import GitRepo
from lichoscli.core.services import PackageService, SubmoduleService
from lichoscli.utils import CI_PKG, CORE_PACKAGES
from lichoscli.utils.constants import BUILD_IMAGE_PKG

logger = logging.getLogger(__name__)


class ReleaseCommand(Command):
    """Create and manage releases by updating submodules, verifying builds, creating snapshots and tagging"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.submodule_service = di_container.obtain_ref(SubmoduleService)

    def validate_args(self) -> None:
        """Validate that required arguments are provided"""
        if not getattr(self.args, "branch_explicitly_provided", False):
            raise ValueError("--branch is required for the release command")

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument(
            "--rms-url",
            required=True,
            help="Repo Manager Server (Nexus Proxy) URL (required)",
        )
        sp.add_argument(
            "--nexus-url",
            required=True,
            help="Nexus URL (required)",
        )
        sp.add_argument(
            "-p",
            "--submodule-project",
            help="Path or URL to the git project containing package submodules",
        )

    def execute(self) -> int:
        """Execute the release process"""

        packages = self.package_service.get_all_packages()
        if not self._verify_builds_success(packages):
            logger.error("Build verification failed")
            return 1

        snapshot_tag = self._get_snapshot_tag()
        git_tag = f"v{snapshot_tag}"

        for package_name in (BUILD_IMAGE_PKG, CI_PKG):
            branch = "main" if package_name == CI_PKG else self.args.branch

            if not self._tag_package(package_name, git_tag, branch, self.args.dry):
                logger.error("Failed to tag packages %s", package_name)
                return 1

        if not self._tag_image_projects(git_tag, self.args.branch, self.args.dry):
            logger.error("Failed to tag image projects")
            return 1
            
        if self.args.submodule_project:
            if not self._update_and_tag_submodule_project(self.args.submodule_project, git_tag, self.args.branch):
                logger.error("Failed to update and tag submodule project")
                return 1
    
        if not self._create_snapshot_repository(
            tag=snapshot_tag,
            branch=self.args.branch,
            rms_url=self.args.rms_url,
            nexus_url=self.args.nexus_url,
            dry_run=self.args.dry,
        ):
            logger.error("Failed to create snapshot repository")
            return 1

        logger.info("Release process completed successfully with tag: %s", snapshot_tag)
        return 0

    def _get_snapshot_tag(self) -> str:
        """Generate snapshot tag based on current date"""
        date_str = datetime.now().strftime("%Y%m%d")
        tag = date_str
        logger.debug("Generated snapshot tag: %s", tag)
        return tag

    def _update_and_tag_submodule_project(self, project_location: str, tag: str, branch: str) -> bool:
        """Fetch/Update submodule project, update submodules to latest, and tag it"""
        logger.info("Updating and tagging submodule project at %s", project_location)

        git_repo = GitRepo.get_or_clone(project_location, branch)
        if not git_repo:
            return False

        committed = False
        if self.args.dry:
            logger.info("DRY RUN: Would synchronize submodules with workspace %s", branch)
        else:
            try:
                committed = bool(self.submodule_service.update(git_repo.path, branch))
            except (BranchError, ValidationError) as e:
                logger.error("%s", e)
                return False

        if not git_repo.create_and_push_tag(tag, message=f"Release {tag}", dry_run=self.args.dry):
            logger.error("Failed to tag submodule project")
            return False

        if committed and not self.args.dry:
            if not git_repo.push_branch():
                logger.error("Failed to push submodule project changes")
                return False

        return True


    def _tag_package(self, package_name: str, tag: str, branch: str, dry_run: bool) -> bool:
        """Tag a specific package with the snapshot tag

        Args:
            package_name: Name of the package to tag
            tag: The tag name to create
            branch: The branch to create the tag from
            dry_run: Whether to perform a dry run without making changes

        Returns:
            bool: True if tagging was successful, False otherwise
        """
        package = self.package_service.get_package(package_name)
        if not package:
            logger.error("Package '%s' not found", package_name)
            return False

        return self._tag_project(package, tag, branch, dry_run)

    def _tag_image_projects(self, tag: str, branch: str, dry_run: bool) -> bool:
        """Tag all image and oci projects available on the release branch."""
        image_projects = [
            project for project in self.package_service.get_packages_by_branch(branch)
            if project.is_image or project.is_oci
        ]

        if not image_projects:
            logger.info("No image or oci projects found on branch '%s'", branch)
            return True

        logger.info("Tagging %d image and oci projects with tag '%s'", len(image_projects), tag)

        for project in sorted(image_projects, key=lambda item: item.name):
            if not self._tag_project(project, tag, branch, dry_run):
                logger.error("Failed to tag image project '%s'", project.name)
                return False

        return True

    def _tag_project(self, project, tag: str, branch: str, dry_run: bool) -> bool:
        """Tag an already resolved project with the snapshot tag."""
        logger.info("Tagging project '%s' with tag '%s'", project.name, tag)

        if dry_run:
            logger.info(
                "DRY RUN: Would create tag '%s' on project '%s' from branch '%s'",
                tag,
                project.name,
                branch,
            )
            return True

        if self._tag_already_exists(project, tag, project.name):
            return True

        return self._create_new_tag(project, tag, branch, project.name)

    def _tag_already_exists(self, package, tag: str, package_name: str) -> bool:
        """Check if tag already exists for the package"""
        try:
            existing_tag = package.tags.get(tag)
            if existing_tag:
                logger.warning("Tag '%s' already exists for package '%s'", tag, package_name)
                return True
        except ProviderAPIError:
            # Tag doesn't exist, which is expected for new tags
            pass
        return False

    def _create_new_tag(self, package, tag: str, branch: str, package_name: str) -> bool:
        """Create a new tag for the package"""

        try:
            package.tags.create(name=tag, target=branch, message=f"Release snapshot {tag}")
            logger.info("Successfully created tag '%s' for package '%s'", tag, package_name)
            return True
        except ProviderAPIError as e:
            logger.error(
                "Failed to create tag '%s' for package '%s': %s",
                tag,
                package_name,
                str(e),
            )
            return False

    def _create_snapshot_repository(self, tag: str, branch: str, rms_url: str, nexus_url: str, dry_run: bool) -> bool:
        """Create branch snapshot repository using the repository API

        Args:
            tag: The snapshot tag to use
            branch: The branch name for repository naming
            rms_url: The RMS service URL
            nexus_url: The Nexus repository URL
            dry_run: Whether to perform a dry run without making changes

        Returns:
            bool: True if snapshot repository creation was successful, False otherwise
        """
        # Create repository name following the schema: <branch>-snapshot-<tag>
        repo_name = f"{branch}-snapshot-{tag}"
        logger.info("Creating branch snapshot repository with name: %s", repo_name)

        rms_token = os.environ.get("RMS_PLATFORM_TOKEN")

        if not rms_token:
            logger.error("RMS_PLATFORM_TOKEN environment variable is not set")
            return False

        url = f"{rms_url}/v1/repositories/apt/snapshot"
        headers = {
            "Authorization": f"Bearer {rms_token}",
            "Content-Type": "application/json",
        }

        data = {
            "suffix": tag,
            "repo_url": f"{nexus_url}/repository/{branch}/",
            "distribution": branch,
            "component": "main",
            "blob_store": f"{branch}",
        }

        if dry_run:
            logger.info("DRY RUN: Would create snapshot repository with data: %s", data)
            return True

        try:
            logger.debug("Making POST request to: %s", url)
            logger.debug("Request data: %s", data)

            response = requests.post(url, json=data, headers=headers, timeout=5)

            if response.status_code in [200, 201, 202]:
                logger.info("Snapshot repository creation request submitted successfully")
                logger.debug("Response: %s", response.text)
                return True

            logger.error(
                "Failed to submit snapshot repository creation request. Status: %d, Response: %s",
                response.status_code,
                response.text,
            )
            return False

        except requests.Timeout:
            logger.info(
                "Repository creation request submitted (timed out waiting for response, which is expected for long-running tasks)"
            )
            return True
        except requests.RequestException as e:
            logger.error("Network error while creating snapshot repository: %s", str(e))
            return False

    def _verify_builds_success(self, packages) -> bool:
        """Verify builds and tests for all packages."""
        logger.info("Verifying builds and tests for all packages")

        failed_packages = []

        for package in packages:
            if package.name in CORE_PACKAGES:
                logger.debug("Skipping package: %s", package.name)
                continue
            logger.debug("Checking build status for package: %s", package.name)

            pipeline = package.pipelines.get_latest()

            if not pipeline:
                logger.warning("No pipeline found for package: %s", package.name)
                failed_packages.append(package.name)
                continue

            if not pipeline.status.is_successful:
                logger.error(
                    "Pipeline failed for package %s with status: %s",
                    package.name,
                    pipeline.status.to_string(),
                )
                failed_packages.append(package.name)
                continue

            logger.debug("Package %s build status: %s", package.name, pipeline.status.to_string())

        if failed_packages:
            logger.error(
                "The following packages have failed builds: %s",
                ", ".join(failed_packages),
            )
            return False

        logger.info("All package builds and tests passed successfully")
        return True
