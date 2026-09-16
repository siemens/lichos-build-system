# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
from pathlib import Path

import yaml
from git.exc import GitCommandError
from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.handlers.lichos_anchor import LichosAnchorHandler
from lichoscli.core.models.git.git_url import GitUrl
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class CloneCommand(Command):
    """Clone a package repository"""

    @classmethod
    def prepare_args(cls, args) -> None:
        parsed_url = GitUrl.parse(args.repository)
        if not parsed_url:
            return

        args.host = args.host or parsed_url.host
        args.pkg_group = args.pkg_group or parsed_url.group

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        
        parsed_url = GitUrl.parse(args.repository)
        
        if parsed_url:
            self.is_direct_clone = True
            self.parsed_url = parsed_url
            self.url_group_path = Path(*parsed_url.group.split("/"))
            self.destination = Path(args.directory) if args.directory else None
            self.clone_path = (
                self.destination / parsed_url.package
                if self.destination is not None
                else self.url_group_path / parsed_url.package
            )
            self.local_dir_name = str(self.clone_path)
            self.git_url = parsed_url.clone_url
            logger.debug("Using clone URL: %s", self.git_url)
            
            # Extract branch from URL if present and not already specified
            if parsed_url.branch and not args.branch:
                logger.debug("Extracted branch from URL: %s", parsed_url.branch)
                args.branch = parsed_url.branch
        else:
            self.is_direct_clone = False
            self.parsed_url = None
            self.url_group_path = None
            self.destination = None
            self.clone_path = Path(args.repository)
            self.git_url = None
            self.local_dir_name = args.repository
            logger.debug("Treating as package name: %s", args.repository)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("repository", help="repository name or repository URL")
        sp.add_argument("directory", nargs="?", help="destination directory")

    def execute(self):
        if self.is_direct_clone:
            if not self._validate_package_group():
                return 1
            self.clone_path.parent.mkdir(parents=True, exist_ok=True)

        if os.path.exists(self.local_dir_name):
            logger.error("Directory '%s' already exists", self.local_dir_name)
            return 1

        repository = self._resolve_repository()
        if not repository:
            logger.error("Could not resolve repository '%s'", self.args.repository)
            return 1

        if repository.archived:
            logger.warning("Cloning archived project '%s'", self.local_dir_name)

        repo = self._clone_repository(repository)
        if repo is None:
            return 1

        self._configure_parent_remote(repo, repository)
        self._configure_upstream_remote(repo)

        if self.is_direct_clone:
            branch = self.args.branch or repo.active_branch.name
            lichos_anchor_handler = self.di_container.obtain_ref(LichosAnchorHandler)
            lichos_anchor_handler.write(
                host=self.parsed_url.host,
                pkg_group=self.args.pkg_group or self.parsed_url.group,
                branch=branch,
                target_dir=self._anchor_path(),
            )
            self.output.success(
                "Created .lichos file in '{}' (group={}, branch={})".format(
                    self._anchor_path(), self.args.pkg_group or self.parsed_url.group, branch
                )
            )

        return 0

    def _validate_package_group(self):
        package_group = self.args.pkg_group or self.parsed_url.group
        group_parts = self.parsed_url.group.split("/")
        package_group_parts = package_group.split("/")

        if any(part in ("", ".", "..") for part in group_parts + package_group_parts):
            logger.error("Invalid package group path")
            return False
        if group_parts[:len(package_group_parts)] != package_group_parts:
            logger.error(
                "Package group '%s' is not a prefix of URL group '%s'",
                package_group,
                self.parsed_url.group,
            )
            return False
        return True

    def _anchor_path(self):
        if self.destination is not None:
            return self.destination
        package_group = self.args.pkg_group or self.parsed_url.group
        return Path(*package_group.split("/"))

    def _resolve_repository(self):
        package_service = self.di_container.obtain_ref(PackageService)

        if self.is_direct_clone:
            return package_service.get_project_by_url(self.parsed_url.web_url)

        repository = package_service.get_package(
            self.local_dir_name, include_archived=True
        )
        if not repository:
            logger.error("Package '%s' not found", self.local_dir_name)
        return repository

    def _clone_repository(self, repository):
        repo_url = repository.ssh_url_to_repo
        logger.info("Cloning %s to %s", repo_url, self.local_dir_name)

        if self.args.branch:
            try:
                repo = Repo.clone_from(repo_url, self.local_dir_name, branch=self.args.branch)
            except GitCommandError as e:
                logger.warning("Failed to checkout %s: %s", self.args.branch, e)
                logger.warning(
                    "Checkout default branch and create local branch %s",
                    self.args.branch,
                )
                try:
                    repo = Repo.clone_from(repo_url, self.local_dir_name, branch=repository.default_branch)
                except GitCommandError as fallback_error:
                    logger.error("Failed to clone default branch %s: %s", repository.default_branch, fallback_error)
                    return None
                repo.git.checkout("-b", self.args.branch)
        else:
            repo = Repo.clone_from(repo_url, self.local_dir_name, branch=repository.default_branch)

        return repo

    def _configure_parent_remote(self, repo, repository):
        if repository.is_fork:
            purl = repository.parent_ssh_url_to_repo
            if purl:
                logger.debug("Adding parent %s", purl)
                parent = repo.create_remote("parent", purl)
                parent.fetch()

    def _configure_upstream_remote(self, repo):
        fn = os.path.join(self.local_dir_name, "debian/upstream/metadata")
        if os.path.exists(fn):
            logger.debug("Found upstream metadata %s", fn)
            with open(fn, encoding="utf-8") as fh:
                y = yaml.safe_load(fh)
                if u := y.get("Repository", None):
                    logger.debug("Adding upstream %s", u)
                    upstream = repo.create_remote("upstream", u)
                    upstream.fetch()

        return 0
