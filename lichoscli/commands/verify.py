import logging
from typing import Any, Callable

from rich.table import Table

from lichoscli.commands.base import Command
from lichoscli.core.exceptions import ProjectFetchingError
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class VerifyCommand(Command):
    """Verify that all packages have valid settings"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.detailed = args.detailed
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="Verify specific package (optional)")
        sp.add_argument(
            "-d",
            "--detailed",
            action="store_true",
            help="Show detailed validation results",
        )

    def execute(self) -> int:
        if self.package_name:
            return self.verify_package(self.package_name)
        return self.verify_all_packages()

    def verify_package(self, package_name: str) -> int:
        package = self.package_service.get_package(package_name)
        if not package:
            logger.error("Package '%s' not found", package_name)
            return 1

        violations = self.validate_package_settings(package)

        if violations:
            self.console.print(f"[red]Package '{package_name}' has validation errors:[/red]")
            for violation in violations:
                self.console.print(f"  - {violation}")
            return 1

        self.console.print(f"[green]Package '{package_name}' passed all validations[/green]")
        return 0

    def verify_all_packages(self) -> int:
        packages = self.package_service.get_all_packages()

        if not packages:
            logger.error("No packages found")
            return 1

        results = []
        total_violations = 0

        for package in packages:
            violations = self.validate_package_settings(package)
            status = "PASS" if not violations else "FAIL"
            violation_count = len(violations)
            total_violations += violation_count

            details = "\n".join(violations) if self.detailed and violations else ""

            results.append(
                [
                    package.name,
                    status,
                    violation_count,
                    details if self.detailed else None,
                ]
            )

        if self.detailed:
            table = Table(title="Package Verification Results")
            table.add_column("Package", no_wrap=True)
            table.add_column("Status")
            table.add_column("Issues", justify="center")
            table.add_column("Details", max_width=80)

            for package_name, status, violation_count, details in results:
                status_color = "[green]" if status == "PASS" else "[red]"
                table.add_row(
                    package_name,
                    f"{status_color}{status}[/{status_color}]",
                    str(violation_count),
                    details or "",
                )

            self.console.print(table)
        else:
            table = Table(title="Package Verification Results")
            table.add_column("Package", no_wrap=True)
            table.add_column("Status")
            table.add_column("Issues", justify="center")

            for package_name, status, violation_count in [row[:3] for row in results]:
                status_color = "[green]" if status == "PASS" else "[red]"
                table.add_row(
                    package_name,
                    f"{status_color}{status}[/{status_color}]",
                    str(violation_count),
                )

            self.console.print(table)

        total_packages = len(packages)
        failed_packages = sum(1 for result in results if "FAIL" in result[1])

        self.console.print(
            f"\n[blue]Summary: {total_packages - failed_packages}/{total_packages} packages passed validation[/blue]"
        )

        if total_violations > 0:
            self.console.print(f"[yellow]Total validation issues found: {total_violations}[/yellow]")
            return 1

        self.console.print("[green]All packages passed validation[/green]")
        return 0

    def validate_package_settings(self, package) -> list[str]:
        """
        Validate a package against all defined settings.
        Returns a list of violation messages.
        """
        violations = []

        settings_validations = self.get_settings_validations()

        for setting_name, validator_func in settings_validations.items():
            try:
                is_valid, error_message = validator_func(package)
                if not is_valid:
                    violations.append(f"{setting_name}: {error_message}")
            except (AttributeError, TypeError, ValueError) as e:
                violations.append(f"{setting_name}: validation error - {str(e)}")
                logger.debug("Error validating %s for %s: %s", setting_name, package.name, e)

        return violations

    def get_settings_validations(self) -> dict[str, Callable[[Any], tuple[bool, str]]]:
        """
        Define all validation rules here.
        Each validator function takes a package and returns (is_valid, error_message).
        Add new validations here to extend the verify command.
        """
        return {
            "default_branch_name": self._validate_default_branch_name,
            "default_branch_protected": self._validate_default_branch_protected,
            "default_branch_force_push": self._validate_default_branch_force_push,
            "protected_branches_no_push": self._validate_protected_branches_no_push,
            "ci_config_path": self._validate_ci_config_path,
        }

    def _validate_default_branch_name(self, package) -> tuple[bool, str]:
        """Validate that the default branch is named 'Flocken'"""
        expected_branch = "flocken"
        actual_branch = package.default_branch

        if actual_branch != expected_branch:
            return False, f"expected '{expected_branch}', got '{actual_branch}'"
        return True, ""

    def _validate_default_branch_protected(self, package) -> tuple[bool, str]:
        """Validate that the default branch is protected"""
        default_branch = package.default_branch
        if not default_branch:
            return False, "no default branch set"

        try:
            protected_branches = package.protectedbranches.list()
            protected_branch_names = [pb.name for pb in protected_branches]

            if default_branch not in protected_branch_names:
                return False, f"default branch '{default_branch}' is not protected"
            return True, ""
        except ProjectFetchingError as e:
            return False, f"could not check protected branches: {str(e)}"

    def _validate_default_branch_force_push(self, package) -> tuple[bool, str]:
        """Validate that the default branch does not allow force push"""
        default_branch = package.default_branch
        if not default_branch:
            return False, "no default branch set"

        try:
            protected_branches = package.protectedbranches.list()

            for pb in protected_branches:
                if pb.name == default_branch:
                    force_push_allowed = pb.allow_force_push

                    if force_push_allowed:
                        return (
                            False,
                            f"default branch '{default_branch}' allows force push",
                        )
                    return True, ""

            return False, f"default branch '{default_branch}' is not protected"
        except ProjectFetchingError as e:
            return False, f"could not check force push settings: {str(e)}"

    def _validate_protected_branches_no_push(self, package) -> tuple[bool, str]:
        """Validate that protected branches do not allow direct push access"""
        try:
            branches_with_push = package.has_protected_branches_with_push_access()

            if branches_with_push:
                branch_list = ", ".join(f"'{b}'" for b in branches_with_push)
                return (
                    False,
                    f"protected branches allow push access: {branch_list}",
                )
            return True, ""
        except Exception as e:
            return False, f"could not check protected branch push access: {str(e)}"

    def _validate_ci_config_path(self, package) -> tuple[bool, str]:
        ci_config_path = package.ci_config_path

        if not ci_config_path:
            return False, "CI config path is not set"

        if ci_config_path == ".gitlab-ci.yml":
            return False, "CI config path is set to default local file"

        return True, ""
