from abc import ABC, abstractmethod
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from typing import Dict, Optional

from lichoscli.core.models.build import BuildParameters


@dataclass
class BuildEnvironment:
    """Build environment configuration."""

    variables: Dict[str, str]
    image: str
    repo_setup_cmd: str
    build_cmd: str

    @property
    def full_script(self) -> str:
        """Get the complete build script combining setup and build commands."""
        return f"{self.repo_setup_cmd} ; {self.build_cmd}"


class EnvironmentService(ABC):
    """Abstract interface for build environment management."""

    @abstractmethod
    def prepare_build_environment(
        self, package_name: str, branch: str, base_environment: Dict[str, str]
    ) -> Optional[BuildEnvironment]:
        """
        Prepare the complete build environment for a package.

        Args:
            package_name: Name of the package to build
            branch: Branch to build from
            base_environment: Base environment variables

        Returns:
            BuildEnvironment with all necessary configuration, or None if preparation failed
        """

    @abstractmethod
    def create_environment_file(self, environment: Dict[str, str]) -> Optional[NamedTemporaryFile]:
        """
        Create a temporary file containing environment variables.

        Args:
            environment: Dictionary of environment variables

        Returns:
            NamedTemporaryFile with environment variables, or None if creation failed
        """

    @abstractmethod
    def expand_environment_variables(self, environment: Dict[str, str]) -> Dict[str, str]:
        """
        Expand environment variables that reference other variables.

        Args:
            environment: Environment variables to expand

        Returns:
            Dictionary with expanded environment variables
        """

    @abstractmethod
    def create_build_environment_from_config(
        self, build_config: BuildParameters, package_variables: Dict[str, str] = None
    ) -> Dict[str, str]:
        """
        Create environment variables from BuildConfig in a provider-agnostic way.

        Args:
            build_config: BuildConfig containing build parameters
            package_variables: Optional package-specific variables

        Returns:
            Dictionary of environment variables
        """
