# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProjectFetchingError
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class SetForkedCommand(Command):
    """Set fork relationship to a parent project"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="some package name")
        sp.add_argument("parent", help="parent package")

    def execute(self):
        pn = BuildUtils.get_package_name(self.args.package)
        pkg = None
        if pn:
            pkg = self.package_service.get_package(pn)

        if pn is None or pkg is None:
            logger.error("Can't find %s", pn)
            return 1

        try:
            # Get parent package by full path
            parent_pkg = self.package_service.get_package(self.args.parent)
            if not parent_pkg:
                logger.error("Parent package '%s' not found", self.args.parent)
                return 1
        except ProjectFetchingError as e:
            logger.error("%s: %s", self.args.parent, e)
            return 1

        try:
            pkg.create_fork_relation(parent_pkg.id)
        except ProjectFetchingError as e:
            logger.error("%s: %s", pn, e)
            return 1

        return 0
