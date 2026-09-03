# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class RemoveCommand(Command):
    """Delete a package"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="package name")

    def execute(self) -> int:
        package = self.package_service.get_package(self.package_name)
        if package is None:
            logger.error("Package '%s' not found", self.package_name)
            return 1

        if package.is_marked_for_deletion:
            # A bare delete() would be rejected -- it's already marked. Only
            # delete_permanently() (via re-fetching its current path) works now.
            self.output.warning("'{}' is already marked for deletion.".format(package.name))
            return self._permanently_delete(package)

        if not self._confirm(package, "delete"):
            self.output.muted("Aborted, nothing was deleted.")
            return 1

        if not package.delete():
            self.output.error("Failed to delete '{}'".format(package.path_with_namespace))
            return 1
        self.output.success("Package '{}' deleted.".format(package.name))

        if not self.prompts.confirm(
            "Also permanently remove '{}' from the archive right now? "
            "This skips any retention period and cannot be undone.".format(package.name),
            default=False,
        ):
            self.output.muted("Left in the archive; it may be purged automatically later.")
            return 0

        return self._permanently_delete(package)

    def _permanently_delete(self, package) -> int:
        if not self._confirm(package, "permanently delete"):
            self.output.muted("Aborted, package remains in the archive.")
            return 0

        if not package.delete_permanently():
            self.output.error("Failed to permanently delete '{}'".format(package.path_with_namespace))
            return 1
        self.output.success("Package '{}' permanently removed.".format(package.name))
        return 0

    def _confirm(self, package, verb: str) -> bool:
        self.output.danger(
            "This will {} '{}' ({}).".format(verb, package.path_with_namespace, package.web_url)
        )
        typed = self.prompts.text_input("Type the package name ('{}') to confirm".format(package.name))
        return typed == package.name
