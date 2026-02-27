# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os

import yaml
from git.exc import GitCommandError
from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.models.git.git_url import GitUrl
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class CloneCommand(Command):
    """Clone a package repository"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        
        parsed_url = GitUrl.parse(args.repository)
        
        if parsed_url:
            self.is_direct_clone = True
            self.local_dir_name = parsed_url.package
            self.git_url = parsed_url.clone_url
            logger.debug("Using clone URL: %s", self.git_url)
            
            # Extract branch from URL if present and not already specified
            if parsed_url.branch and not args.branch:
                logger.debug("Extracted branch from URL: %s", parsed_url.branch)
                args.branch = parsed_url.branch
        else:
            self.is_direct_clone = False
            self.git_url = None
            self.local_dir_name = args.repository
            logger.debug("Treating as package name: %s", args.repository)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("repository", help="repository name or repository URL")

    def execute(self):
        if os.path.exists(self.local_dir_name):
            logger.error("Directory '%s' already exists", self.local_dir_name)
            return 1

        if self.is_direct_clone:
            # Direct clone from URL (no API access needed)
            return self._execute_direct_clone()
        else:
            # API-based clone using package name
            return self._execute_api_clone()

    def _execute_direct_clone(self):
        """Clone directly from a git URL without API access."""
        logger.info("Cloning from %s to %s", self.git_url, self.local_dir_name)
        
        if self.args.branch:
            try:
                repo = Repo.clone_from(self.git_url, self.local_dir_name, branch=self.args.branch)
            except GitCommandError as e:
                logger.error("Failed to clone branch %s: %s", self.args.branch, e)
                return 1
        else:
            repo = Repo.clone_from(self.git_url, self.local_dir_name)
        
        # Check for upstream metadata (debian/upstream/metadata)
        # This can still be configured without API access
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

    def _execute_api_clone(self):
        """Clone using API to get repository information from package name."""
        # Only obtain PackageService when we need it (lazy initialization)
        package_service = self.di_container.obtain_ref(PackageService)
        repository = package_service.get_package(self.local_dir_name)
        if not repository:
            logger.error("Package '%s' not found", self.local_dir_name)
            return 1

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
                repo = Repo.clone_from(repo_url, self.local_dir_name, branch=repository.default_branch)
                repo.git.checkout("-b", self.args.branch)
        else:
            repo = Repo.clone_from(repo_url, self.local_dir_name, branch=repository.default_branch)

        if repository.is_fork:
            purl = repository.parent_ssh_url_to_repo
            if purl:
                logger.debug("Adding parent %s", purl)
                parent = repo.create_remote("parent", purl)
                parent.fetch()

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
