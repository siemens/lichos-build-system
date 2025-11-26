#!/usr/bin/python3

import logging
import os
from datetime import datetime

import requests
from gitlab.exceptions import GitlabError

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
from lichoscli.utils import CI_PKG, CORE_PACKAGES

logger = logging.getLogger(__name__)


class ReleaseCommand(Command):
    """Create and manage releases by updating submodules, verifying builds, creating snapshots and tagging"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)

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

    def execute(self) -> int:
        """Execute the release process"""

        packages = self.package_service.get_all_packages()
        if not self._verify_builds_success(packages):
            logger.error("Build verification failed")
            return 1

        snapshot_tag = self._get_snapshot_tag()
        git_tag = f"v{snapshot_tag}"

        for package_name in CORE_PACKAGES:
            branch = "main" if package_name == CI_PKG else self.args.branch

            if not self._tag_package(package_name, git_tag, branch, self.args.dry):
                logger.error("Failed to tag packages %s", package_name)
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
        logger.info("Tagging package '%s' with tag '%s'", package_name, tag)

        package = self.package_service.get_package(package_name)
        if not package:
            logger.error("Package '%s' not found", package_name)
            return False

        if dry_run:
            logger.info(
                "DRY RUN: Would create tag '%s' on package '%s' from branch '%s'",
                tag,
                package_name,
                branch,
            )
            return True

        if self._tag_already_exists(package, tag, package_name):
            return True

        return self._create_new_tag(package, tag, branch, package_name)

    def _tag_already_exists(self, package, tag: str, package_name: str) -> bool:
        """Check if tag already exists for the package"""
        try:
            existing_tag = package.tags.get(tag)
            if existing_tag:
                logger.warning("Tag '%s' already exists for package '%s'", tag, package_name)
                return True
        except GitlabError:
            # Tag doesn't exist, which is expected for new tags
            pass
        return False

    def _create_new_tag(self, package, tag: str, branch: str, package_name: str) -> bool:
        """Create a new tag for the package"""

        try:
            package.tags.create(name=tag, target=branch, message=f"Release snapshot {tag}")
            logger.info("Successfully created tag '%s' for package '%s'", tag, package_name)
            return True
        except GitlabError as e:
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
