# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import subprocess

from lichoscli.commands.base import Command
from lichoscli.core.models.git import GitRepo
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class BrowseCommand(Command):
    """Open package in web browser"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")

    def execute(self):
        pkg = self.package_service.get_package(self.package_name)
        if pkg is None:
            logger.error("Package not found: %s", self.package_name)
            return 1

        url = pkg.web_url
        if self.args.branch is None:
            repo = GitRepo.auto_detect(package_name=self.package_name)
            branch = repo.active_branch if repo is not None else None
        else:
            branch = self.args.branch

        if branch:
            url = f"{url}/tree/{branch}"

        logger.info("Opening URL: %s", url)

        r = subprocess.run(("xdg-open", url), check=True)
        return r.returncode
