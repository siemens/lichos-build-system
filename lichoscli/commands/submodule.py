# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from pathlib import Path

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import BranchError, ServiceError, ValidationError
from lichoscli.core.models.git import GitUrl
from lichoscli.core.services import SubmoduleService

logger = logging.getLogger(__name__)


class SubmoduleCommand(Command):
    """Manage git submodule projects with all packages in a flattened hierarchy"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.submodule_service = di_container.obtain_ref(SubmoduleService)

    @classmethod
    def add_arguments(cls, sp):
        subparsers = sp.add_subparsers(dest="subcommand", help="submodule operations")

        # Create subcommand
        create_parser = subparsers.add_parser("create", help="create a new submodule project")
        create_parser.add_argument("project_name", help="name of the submodule project to create")
        create_parser.add_argument(
            "--output-dir",
            "-o",
            default=".",
            help="output directory for the project (default: current directory)",
        )
        create_parser.add_argument(
            "--push",
            action="store_true",
            default=False,
            help="push changes to remote repository after creating the project",
        )

        # Update subcommand
        update_parser = subparsers.add_parser("update", help="update existing submodule project")
        update_parser.add_argument("path", help="path to existing submodule project to update")
        update_parser.add_argument(
            "--push",
            action="store_true",
            default=False,
            help="push changes to remote repository after updating",
        )

    def execute(self):
        """Execute the submodule command based on the specified subcommand."""
        args = self.args
        try:
            if args.subcommand == "create":
                origin = GitUrl(host=args.host, group=self.di_container.group_rpath, package=args.project_name)
                path = Path(args.output_dir) / args.project_name
                changes = self.submodule_service.create(path, args.branch, origin.clone_url, args.push)
            elif args.subcommand == "update":
                changes = self.submodule_service.update(Path(args.path).resolve(), args.branch, args.push)
            else:
                logger.error("Invalid subcommand: %s. Use 'create' or 'update'", args.subcommand)
                return 1
        except (BranchError, ServiceError, ValidationError) as e:
            logger.error("%s", e)
            return 1

        for change in changes:
            logger.info("%s submodule '%s'", change.kind.capitalize(), change.path)
        if not changes:
            logger.info("All submodules are already up to date")
        elif not args.push:
            logger.info("Changes have been committed locally. Use --push to push to remote repository.")
        return 0
