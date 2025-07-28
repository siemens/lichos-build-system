import logging
from typing import Dict, Callable, Any, List, Tuple
from gitlab import GitlabError
from tabulate import tabulate

from lichoscli.commands.base import Command
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class VerifyCommand(Command):
    """Verify that all packages have valid settings"""

    def __init__(self, pkg_group_handler, args):
        super().__init__(pkg_group_handler, args)
        self.package_name = BuildUtils.get_package_name(args.package) if hasattr(args, 'package') and args.package else None
        self.detailed = args.detailed if hasattr(args, 'detailed') else False

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="Verify specific package (optional)")
        sp.add_argument("-d", "--detailed", action="store_true", 
                   help="Show detailed validation results")

    def execute(self) -> int:
        if self.package_name:
            return self.verify_package(self.package_name)
        return self.verify_all_packages()

    def verify_package(self, package_name: str) -> int:
        package = self.pkg_group_handler.get_package(package_name)
        if not package:
            logger.error(f"Package '{package_name}' not found")
            return 1

        violations = self.validate_package_settings(package)
        
        if violations:
            print(f"Package '{package_name}' has validation errors:")
            for violation in violations:
                print(f"  - {violation}")
            return 1
        
        print(f"Package '{package_name}' passed all validations")
        return 0

    def verify_all_packages(self) -> int:
        packages = self.pkg_group_handler.get_all_packages()
        
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
            
            results.append([
                package.name,
                status,
                violation_count,
                details if self.detailed else None
            ])

        if self.detailed:
            headers = ["Package", "Status", "Issues", "Details"]

            print(tabulate(results, headers=headers, tablefmt="grid", 
                          maxcolwidths=[None, None, None, 80]))
        else:
            headers = ["Package", "Status", "Issues"]
            results = [[row[0], row[1], row[2]] for row in results]
            print(tabulate(results, headers=headers, tablefmt="grid"))
        
        total_packages = len(packages)
        failed_packages = sum(1 for _, status, _, _ in results if "FAIL" in status)
        
        print(f"\nSummary: {total_packages - failed_packages}/{total_packages} packages passed validation")
        
        if total_violations > 0:
            print(f"Total validation issues found: {total_violations}")
            return 1
        
        print("All packages passed validation")
        return 0

    def validate_package_settings(self, package) -> List[str]:
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
                logger.debug(f"Error validating {setting_name} for {package.name}: {e}")
        
        return violations

    def get_settings_validations(self) -> Dict[str, Callable[[Any], Tuple[bool, str]]]:
        """
        Define all validation rules here.
        Each validator function takes a package and returns (is_valid, error_message).
        Add new validations here to extend the verify command.
        """
        return {
            "default_branch_name": self._validate_default_branch_name,
            "default_branch_protected": self._validate_default_branch_protected,
            "default_branch_force_push": self._validate_default_branch_force_push,
            "ci_config_path": self._validate_ci_config_path,
        }

    def _validate_default_branch_name(self, package) -> Tuple[bool, str]:
        """Validate that the default branch is named 'Flocken'"""
        expected_branch = "flocken"
        actual_branch = getattr(package, 'default_branch', None)
        
        if actual_branch != expected_branch:
            return False, f"expected '{expected_branch}', got '{actual_branch}'"
        return True, ""

    def _validate_default_branch_protected(self, package) -> Tuple[bool, str]:
        """Validate that the default branch is protected"""
        default_branch = getattr(package, 'default_branch', None)
        if not default_branch:
            return False, "no default branch set"
        
        try:
            protected_branches = package.protectedbranches.list()
            protected_branch_names = [pb.name for pb in protected_branches]
            
            if default_branch not in protected_branch_names:
                return False, f"default branch '{default_branch}' is not protected"
            return True, ""
        except GitlabError as e:
            return False, f"could not check protected branches: {str(e)}"

    def _validate_default_branch_force_push(self, package) -> Tuple[bool, str]:
        """Validate that the default branch does not allow force push"""
        default_branch = getattr(package, 'default_branch', None)
        if not default_branch:
            return False, "no default branch set"
        
        try:
            protected_branches = package.protectedbranches.list()
            
            for pb in protected_branches:
                if pb.name == default_branch:
                    force_push_allowed = getattr(pb, 'allow_force_push', True) 
                    
                    if force_push_allowed:
                        return False, f"default branch '{default_branch}' allows force push"
                    return True, ""
            
            return False, f"default branch '{default_branch}' is not protected"
        except GitlabError as e:
            return False, f"could not check force push settings: {str(e)}"

    def _validate_ci_config_path(self, package) -> Tuple[bool, str]:
        ci_config_path = getattr(package, 'ci_config_path', None)
        
        if not ci_config_path:
            return False, "CI config path is not set"
        
        if ci_config_path == '.gitlab-ci.yml':
            return False, "CI config path is set to default local file"
        
        return True, ""
