import logging
import os
import random
import subprocess
from typing import Optional

import git
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils, GitUtils

logger = logging.getLogger(__name__)


class BuildCommand(Command):
    """build package"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler, args)
        self.ci_project_dir = self._determine_project_dir(args.shell)

        self.package_name = BuildUtils.get_package_name(args.package)
        self.package = self.pkg_group_handler.get_package(self.package_name)
        self.group = args.pkg_group or GitUtils.get_group()
        self.branch = BuildUtils.get_branch_name(args.branch)
        self.shell = args.shell
        self.architecture = BuildUtils.normalize_architecture(args.architecture)
        self.enable_cross = args.enable_cross
        self.build_arch = BuildUtils.normalize_architecture(os.uname().machine)

        if self.enable_cross: 
            self.platform = f"linux/{self.build_arch}"
        else:
            self.platform = f"linux/{self.architecture}"
            
        self.branch_ref_slug = GitUtils.get_ref_slug(self.branch)
        self.build_env = self._build_environment()
        self.profile = args.profile
        self.network = args.network

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument(
            "--architecture",
            nargs="?",
            default=os.uname().machine,
            help="architecture to build for",
        )
        sp.add_argument("--script", help="force different script")
        sp.add_argument(
            "--shell",
            action="store_true",
            default=False,
            help="launch shell instead of executing build command",
        )
        sp.add_argument(
            "--enable-cross",
            action="store_true",
            help="option to enable cross compilation setup",
        )
        sp.add_argument("--profile", nargs="?", help="debian profile to build")
        sp.add_argument("--network", nargs="?", help="docker network to use for the container")

    def execute(self):
        if not self.package:
            logger.error("Package '%s' not found", self.package_name)
            return 1
            
        print(f"Building package: {self.package.name}")
        print(f"Architecture: {self.architecture}")

        repo = GitUtils.get_git_repo()
        if repo and GitUtils.has_submodules(repo):
            print("Submodules detected, initializing...")
            if not GitUtils.initialize_submodules(repo):
                logger.error("Failed to initialize submodules")
                return 1

        try:
            env_file = self._prepare_build_environment()
            if not env_file:
                return 1

            docker_config = self._extract_docker_config(env_file)
            if not docker_config:
                return 1

            cmd = self._build_docker_command(docker_config)

            pull_result = BuildUtils.pull_docker_image(image=docker_config["image"])
            if pull_result != 0:
                print(f"Failed to pull Docker image: {docker_config['image']}")
                return pull_result

            return subprocess.run(cmd, check=False).returncode

        finally:
            env_file = locals().get("env_file")
            if env_file:
                os.unlink(env_file.name)

    def _determine_project_dir(self, is_shell_mode: bool) -> str:
        """Determine the project directory path based on shell mode."""
        shell_project_dir = "/build"
        if is_shell_mode:
            return shell_project_dir
        else:
            return "/" + "".join(
                random.sample(shell_project_dir[1:], k=len(shell_project_dir[1:]))
            )

    def _build_environment(self) -> dict:
        """Build the complete environment dictionary for the build process."""
        env = self.pkg_group_handler.get_package_variables(self.package)

        base_env = {
            "CI_PROJECT_DIR": self.ci_project_dir,
            "CI_COMMIT_BRANCH": self.branch,
            "CI_COMMIT_REF_NAME": self.branch,
            "CI_COMMIT_REF_SLUG": self.branch_ref_slug,
            "CI_PROJECT_NAMESPACE": self.group,
            "ARCHITECTURE": self.architecture,
        }

        cross_compilation_env = (
            self._get_cross_compilation_env() if self.enable_cross else {}
        )
        profile_env = self._get_profile_env()

        env.update(base_env)
        env.update(cross_compilation_env)
        env.update(profile_env)

        return env

    def _get_cross_compilation_env(self) -> dict:
        """Get environment variables for cross-compilation setup."""
        return {"ARCHITECTURE": self.build_arch, "DEB_HOST_ARCH": self.architecture}

    def _get_profile_env(self) -> dict:
        """Get environment variables for build profile."""
        if hasattr(self, "profile") and self.profile:
            return {"DEB_BUILD_PROFILES": self.profile}
        return {}

    def _prepare_build_environment(self):
        """Prepare the build environment by fetching artifacts and creating env file."""
        if not self.package:
            logger.error("Package '%s' not found", self.package_name)
            return None
            
        tmpdir = self.pkg_group_handler.get_job_artifacts(
            branch_name=self.branch, package=self.package, job_name="calculate-env"
        )
        if not tmpdir:
            logger.error("Failed to download build artifacts for package '%s' on branch '%s'" % (self.package.name, self.branch))
            logger.error("This usually means no pipeline has been triggered for this branch.")
            logger.error("Please ensure a pipeline exists for branch '%s' in the GitLab project." % self.branch)
            logger.error("Project URL: %s" % self.package.web_url)
            return None

        env = BuildUtils.update_environment_from_file(self.build_env, tmpdir)
        env = BuildUtils.expand_var(env)
        env_file = BuildUtils.create_tmp_env_file(env)

        if not env_file:
            logger.error("Failed to save environment to temporary file.")
            return None

        return env_file

    def _extract_docker_config(self, env_file) -> Optional[dict]:
        """Extract and validate Docker configuration from environment file."""
        with open(env_file.name, "r", encoding="utf-8") as f:
            env_content = f.read()

        env_dict = {}
        for line in env_content.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                env_dict[key] = value

        image = env_dict.get("IMAGE")
        repo_setup = env_dict.get("REPO_SETUP_CMD")
        build_cmd = env_dict.get("BUILD_CMD")

        if not all([image, repo_setup, build_cmd]):
            logger.error(
                "Missing required environment variables (IMAGE, REPO_SETUP_CMD, BUILD_CMD)."
            )
            return None

        return {
            "image": image,
            "script": f"{repo_setup} ; {build_cmd}",
            "env_file": env_file,
        }

    def _build_docker_command(self, docker_config: dict) -> list:
        """Build the Docker command based on configuration and shell mode."""
        cmd = [
            "docker",
            "run",
            "--env-file",
            docker_config["env_file"].name,
            "--rm",
            "-v",
            f"{os.getcwd()}:{self.ci_project_dir}",
            "--platform",
            self.platform,
            "-w",
            self.ci_project_dir,
        ]

        if self.network:
            cmd.extend(["--network", self.network])


        if self.shell:
            cmd.extend(["-it", docker_config["image"], "/usr/bin/bash"])
            BuildUtils.print_build_info(docker_config["script"])
        else:
            cmd.extend(
                [docker_config["image"], "/usr/bin/bash", "-c", docker_config["script"]]
            )

        return cmd
