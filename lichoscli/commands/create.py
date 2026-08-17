# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import textwrap

from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
from lichoscli.utils import CI_DEFAULT_PIPELINE_NAME, BuildUtils

logger = logging.getLogger(__name__)


class CreateCommand(Command):
    """Create a new package"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.package_type = args.type if args.type else CI_DEFAULT_PIPELINE_NAME
        self.branch = args.branch
        self.subgroup = args.subgroup
        self.group_rpath = self.package_service.get_projects().path

    def validate_args(self) -> None:
        """Validate that required arguments are provided"""
        if not getattr(self.args, "branch_explicitly_provided", False):
            raise ValueError("--branch is required for the create command")

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="package name")
        sp.add_argument("type", nargs="?", help="build type")
        sp.add_argument("subgroup", nargs="?", help="subgroup name")

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

        author, repo = self.initialize_package_repository(package, self.package_name)
        logger.info(
            "%s/%s/%s with branch %s created",
            self.group_rpath,
            self.subgroup,
            self.package_name,
            self.branch,
        )

        self.output.success("Package created successfully!")
        self.output.print(f"Remote URL: {package.web_url}")

        if self.package_type == "gbp":
            self.create_debian_package_template(self.package_name, author)

        repo.remotes.origin.push()
        return 0

    @staticmethod
    def initialize_package_repository(package, package_name):
        """Initialize the package repository by cloning and making initial commit."""
        repo_url = package.ssh_url_to_repo
        repo = Repo.clone_from(repo_url, package_name)
        author = repo.index.commit("Initialize package").author
        return author, repo

    @staticmethod
    def create_debian_package_template(package_name, author):
        """Create debian package template files."""
        debian_directory = os.path.join(package_name, "debian")
        debian_source_directory = os.path.join(debian_directory, "source")
        debian_control = os.path.join(debian_directory, "control")
        debian_rules = os.path.join(debian_directory, "rules")
        debian_format = os.path.join(debian_source_directory, "format")

        os.makedirs(debian_source_directory, exist_ok=True)

        CreateCommand.add_default_debian_rules(debian_rules)
        CreateCommand.add_default_debian_control(package_name, author, debian_control)
        CreateCommand.add_default_debian_format(debian_format)

        logger.info("Created debian package template, please adjust the rules and control file as needed")

    @staticmethod
    def add_default_debian_format(debian_format_path):
        """Add default debian format file."""
        with open(debian_format_path, "w", encoding="utf-8") as format_file:
            format_file.write("3.0 (native)\n")

    @staticmethod
    def add_default_debian_control(package_name, author, debian_control_path):
        """Add default debian control file."""
        with open(debian_control_path, "w", encoding="utf-8") as control_file:
            control_file.write(
                textwrap.dedent(
                    """\
                Source: {package}
                Maintainer: {author_name} <{author_email}>
                Build-Depends:
                    debhelper-compat (= 13)
                Standards-Version: 4.6.2

                Package: {package}
                Architecture: any
                Multi-Arch: foreign
                Depends:
                    ${{shlibs:Depends}},
                    ${{misc:Depends}},
                Description: <add your package description here>
                """
                ).format(
                    package=package_name,
                    author_name=author.name,
                    author_email=author.email,
                )
            )

    @staticmethod
    def add_default_debian_rules(debian_rules_path):
        """Add default debian rules file."""
        with open(debian_rules_path, "w", encoding="utf-8") as rules_file:
            rules_file.write(
                textwrap.dedent(
                    """\
                #!/usr/bin/make -f
                %:
                \tdh $@
                """
                )
            )
