import os
import logging
import tempfile
from typing import Dict, Optional

from lichoscli.core.models.build import BuildParameters
from lichoscli.core.services import BuildEnvironment, EnvironmentService, PackageService
from lichoscli.utils import BuildUtils, GitUtils

logger = logging.getLogger(__name__)


class GitLabEnvironmentService(EnvironmentService):
    """GitLab implementation of EnvironmentService."""

    def __init__(self, package_service: PackageService):
        self.package_service = package_service

    def prepare_build_environment(
        self, package_name: str, branch: str, base_environment: Dict[str, str]
    ) -> Optional[BuildEnvironment]:
        """Prepare the complete build environment for a package."""
        try:
            package = self.package_service.get_package(package_name)
            if not package:
                logger.error("Package '%s' not found", package_name)
                return None

            latest_pipeline = package.pipelines.get_latest(branch)
            if not latest_pipeline:
                logger.error(
                    "Failed to find pipeline for package '%s' on branch '%s'",
                    package_name,
                    branch,
                )
                logger.error("This usually means no pipeline has been triggered for this branch.")
                logger.error("Project URL: %s", package.web_url)
                return None

            calculate_env_job = latest_pipeline.jobs.get_by_name("calculate-env")
            if not calculate_env_job:
                logger.error("No calculate-env job found in pipeline")
                return None

            tmpdir = calculate_env_job.artifacts.download_as_directory()
            if not tmpdir:
                logger.error("Failed to download calculate-env artifacts")
                return None

            env = BuildUtils.update_environment_from_file(base_environment, tmpdir)
            env = self.expand_environment_variables(env)

            image = env.get("IMAGE")
            repo_setup = env.get("REPO_SETUP_CMD")
            build_cmd = env.get("BUILD_CMD")

            if not all([image, repo_setup, build_cmd]):
                logger.error("Missing required environment variables (IMAGE, REPO_SETUP_CMD, BUILD_CMD).")
                return None

            return BuildEnvironment(variables=env, image=image, repo_setup_cmd=repo_setup, build_cmd=build_cmd)

        except (OSError, IOError, AttributeError) as e:
            logger.error("Failed to prepare build environment: %s", e)
            return None

    def create_environment_file(self, environment: Dict[str, str]) -> Optional[tempfile.NamedTemporaryFile]:
        """Create a temporary file containing environment variables."""
        try:
            env_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env")

            for key, value in environment.items():
                env_file.write(f"{key}={value}\n")

            env_file.flush()
            logger.debug("Created environment file: %s", env_file.name)
            return env_file

        except (OSError, IOError) as e:
            logger.error("Failed to create environment file: %s", e)
            return None

    def expand_environment_variables(self, environment: Dict[str, str]) -> Dict[str, str]:
        """Expand environment variables that reference other variables."""
        return BuildUtils.expand_var(environment)

    def create_build_environment_from_config(
        self, build_config: BuildParameters, package_variables: Dict[str, str] = None
    ) -> Dict[str, str]:
        """Create environment variables from BuildConfig for GitLab CI/CD compatibility."""
        env = {}

        if package_variables:
            env.update(package_variables)

        env.update(
            {
                "CI_PROJECT_DIR": build_config.project_dir,
                "CI_COMMIT_BRANCH": build_config.branch,
                "CI_COMMIT_REF_NAME": build_config.branch,
                "CI_COMMIT_REF_SLUG": GitUtils.get_ref_slug(build_config.branch),
                "CI_PROJECT_NAMESPACE": build_config.group,
                "ARCHITECTURE": build_config.architecture,
            }
        )

        if build_config.enable_cross:
            build_arch = os.uname().machine
            env.update(
                {
                    "ARCHITECTURE": BuildUtils.normalize_architecture(build_arch),
                    "DEB_HOST_ARCH": build_config.architecture,
                }
            )

        if build_config.profile:
            env["DEB_BUILD_PROFILES"] = build_config.profile

        return env