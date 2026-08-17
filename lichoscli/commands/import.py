# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from git.exc import GitCommandError
from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
from lichoscli.utils import CI_DEFAULT_PIPELINE_NAME, BuildUtils

logger = logging.getLogger(__name__)


class ImportCommand(Command):
    """Import an existing external git repository as a new package

    Creates a brand-new package project in the hierarchy (own permissions, own
    CI config) and seeds it with the source repository's content, instead of
    moving/forking the external GitLab project directly.
    """

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.subgroup, self.package_name = self.split_package_path(args.package)
        self.repository = args.repository
        self.package_type = args.type if args.type else CI_DEFAULT_PIPELINE_NAME
        self.branch = args.branch
        self.group_rpath = self.package_service.get_projects().path

    def validate_args(self) -> None:
        """Validate that required arguments are provided"""
        if not getattr(self.args, "branch_explicitly_provided", False):
            raise ValueError("--branch is required for the import command")

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="destination package path, e.g. new/package/name")
        sp.add_argument("repository", help="URL of the git repository to import")
        sp.add_argument("--type", help="build type")

    def execute(self):
        if BuildUtils.check_local_package_exists(self.package_name):
            return 1

        if self.package_service.get_package(self.package_name) is not None:
            logger.error("%s/%s already exists", self.group_rpath, self.package_name)
            return 1

        package = self.package_service.create_package(
            name=self.package_name,
            branch=self.branch,
            package_type=self.package_type,
            access_level="enabled",
            subgroup=self.subgroup,
        )
        if package is None:
            return 1

        if not package.protect_branch(self.branch):
            return 2

        if not self.clone_and_push(package, self.repository, self.package_name, self.branch):
            return 3

        logger.info(
            "%s/%s imported from %s with branch %s",
            self.group_rpath,
            self.package_name,
            self.repository,
            self.branch,
        )

        self.output.success("Package imported successfully!")
        self.output.print(f"Remote URL: {package.web_url}")
        return 0

    @staticmethod
    def split_package_path(package_path: str):
        """Split a destination path into (subgroup, package_name).

        e.g. "new/package/name" -> ("new/package", "name")
        """
        parts = package_path.split("/")
        name = parts[-1]
        subgroup = "/".join(parts[:-1])
        return subgroup, name

    @staticmethod
    def clone_and_push(package, repository_url, package_name, branch):
        """Clone the source repository and push it as the given package's branch.

        The source is cloned using the URL exactly as given (HTTPS or SSH) since
        external repositories being imported (PoCs, Salsa, ...) are frequently
        only reachable anonymously over HTTPS, unlike our own GitLab hierarchy.
        """
        try:
            repo = Repo.clone_from(repository_url, package_name)
        except GitCommandError as e:
            logger.error("Failed to clone %s: %s", repository_url, e)
            return False

        upstream = repo.remotes.origin
        upstream.rename("upstream")

        origin = repo.create_remote("origin", package.ssh_url_to_repo)

        if repo.active_branch.name != branch:
            repo.git.checkout("-b", branch)

        try:
            origin.push(refspec=f"HEAD:refs/heads/{branch}")
        except GitCommandError as e:
            logger.error("Failed to push imported content to %s: %s", package.ssh_url_to_repo, e)
            return False

        return True
