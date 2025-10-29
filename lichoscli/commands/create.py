import logging
import os
import textwrap

from git.repo import Repo

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProjectFetchingError
from lichoscli.core.services import PackageService
from lichoscli.utils import CI_DEFAULT_PIPELINE_NAME, BuildUtils, GitUtils

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
        if self.check_local_package_exists(self.package_name):
            return 1

        if self.check_remote_package_exists(self.package_service, self.package_name, self.group_rpath):
            return 1

        package = self.create_package(
            self.package_service,
            self.package_name,
            self.branch,
            self.package_type,
            self.subgroup,
            self.group_rpath,
        )
        if package is None:
            return 1

        if not self.protect_branch(package, self.branch):
            return 2

        author, repo = self.initialize_package_repository(package, self.package_name)
        logger.info(
            "%s/%s/%s with branch %s created",
            self.group_rpath,
            self.subgroup,
            self.package_name,
            self.branch,
        )

        print("Package created successfully!")
        print(f"Remote URL: {package.web_url}")

        if self.package_type == "gbp":
            self.create_debian_package_template(self.package_name, author)

        repo.remotes.origin.push()
        return 0

    @staticmethod
    def check_local_package_exists(package_name):
        """Check if a local package directory or file exists."""
        if os.path.exists(package_name):
            logger.error("Please remove the local file or directory '%s' first", package_name)
            return True
        return False

    @staticmethod
    def check_remote_package_exists(package_service, package_name, group_rpath):
        """Check if a remote package already exists."""
        if package_service.get_package(package_name) is not None:
            logger.error("%s/%s already exists", group_rpath, package_name)
            return True
        return False

    @staticmethod
    def create_package(package_service, package_name, branch, package_type, subgroup, group_rpath=None):
        """Create a new package with the given parameters."""
        package = package_service.create_package(
            name=package_name,
            branch=branch,
            package_type=package_type,
            access_level="enabled",
            subgroup=subgroup,
        )
        if package is None:
            logger.error(
                "Failed to create package %s/%s/%s",
                group_rpath or "unknown",
                subgroup,
                package_name,
            )
        return package

    @staticmethod
    def protect_branch(package, branch):
        """Protect the specified branch for the given package."""
        formatted_branch_name = GitUtils.delete_main_from_branch_name(branch)
        try:
            package.protectedbranches.create({"name": formatted_branch_name})
            return True
        except ProjectFetchingError as e:
            logger.error("Failed to protect branch: %s", e)
            return False

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
