# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import random
import subprocess

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models import BuildParameters
from lichoscli.core.models.git import GitRepo
from lichoscli.core.services import (
    ContainerConfig,
    ContainerService,
    EditorConfig,
    EnvironmentService,
    PackageService,
)
from lichoscli.core.services.editor import EditorStrategy
from lichoscli.utils import BuildUtils, ContainerUtils, ProgressUtils

logger = logging.getLogger(__name__)


class BuildCommand(Command):
    """Build a package locally"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)

        self.package_service = di_container.obtain_ref(PackageService)
        self.container_service = di_container.obtain_ref(ContainerService)
        self.environment_service = di_container.obtain_ref(EnvironmentService)
        self.buildparam = self._create_build_config(args)
        self.package = self.package_service.get_package(self.buildparam.package_name)

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
        sp.add_argument("--network", help="docker network to use for the container")
        sp.add_argument(
            "--mount",
            nargs="?",
            help="additional docker mount point (e.g., /host/path:/container/path)",
        )
        sp.add_argument("--profile", nargs="?", help="DEB_BUILD_PROFILES to set for the build")
        sp.add_argument(
            "--editor",
            nargs="?",
            choices=["code"],
            help="launch editor with remote development support (currently only 'code' supported)",
        )
        sp.add_argument(
            "--no-cache",
            action="store_true",
            default=False,
            help="delete old container and start a new one",
        )
        sp.add_argument(
            "--privileged",
            action="store_true",
            default=False,
            help="run container in privileged mode",
        )

    def _create_build_config(self, args) -> BuildParameters:
        """Create BuildConfig from command arguments."""
        package_name = BuildUtils.get_package_name(args.package)
        branch = BuildUtils.get_branch_name(args.branch)
        architecture = BuildUtils.normalize_architecture(args.architecture)
        project_dir = self._determine_project_dir(args.shell, args.editor)
        group = args.pkg_group or GitRepo(".").group
        build_arch = BuildUtils.normalize_architecture(os.uname().machine)
        if self.args.enable_cross:
            platform = f"linux/{build_arch}"
        else:
            platform = f"linux/{architecture}"

        return BuildParameters(
            package_name=package_name,
            architecture=architecture,
            branch=branch,
            group=group,
            project_dir=project_dir,
            enable_cross=args.enable_cross,
            profile=args.profile,
            network=args.network,
            mount=args.mount,
            shell_mode=args.shell,
            editor_mode=args.editor,
            no_cache=args.no_cache,
            privileged=args.privileged,
            custom_script=args.script,
            platform=platform,
        )

    def execute(self):
        if not self.package:
            logger.error("Package '%s' not found", self.buildparam.package_name)
            return 1

        self.output.accent(f"Building package: {self.package.name}")
        self.output.print(f"Architecture: {self.buildparam.architecture}")

        if not self._initialize_submodules():
            return 1

        try:
            package_variables = {}
            if self.package:
                package_variables = self.package.variables.to_dict()
            base_environment = self.environment_service.create_build_environment_from_config(
                self.buildparam, package_variables
            )

            build_environment = self.environment_service.prepare_build_environment(
                self.buildparam.package_name, self.buildparam.branch, base_environment
            )

            if not build_environment:
                logger.error("Failed to prepare build environment")
                return 1

            quote_values: bool = self.buildparam.editor_mode is not None
            env_file = self.environment_service.create_environment_file(build_environment.variables, quote_values)
            if not env_file:
                logger.error("Failed to create environment file")
                return 1

            pull_result = ProgressUtils.execute_with_progress(
                business_logic=lambda: self.container_service.pull_image(build_environment.image),
                description=f"Pulling Docker image: {build_environment.image}",
                console=self.console,
                success_message=f"Successfully pulled Docker image: {build_environment.image}",
                error_message=f"Failed to pull Docker image: {build_environment.image}",
            )
            if pull_result != 0:
                return pull_result

            container_config = self._build_container_config(build_environment, env_file)

            if self.buildparam.editor_mode:
                return self._execute_with_editor(container_config, build_environment)
            else:
                result = self.container_service.run_container(container_config)
                return result.return_code

        finally:
            if "env_file" in locals() and env_file:
                try:
                    os.unlink(env_file.name)
                except OSError:
                    pass

    def _initialize_submodules(self) -> bool:
        """Initialize git submodules if they exist."""
        repo = GitRepo(".")
        if repo.is_valid and repo.has_submodules:
            self.output.print("Submodules detected, initializing...")
            if not repo.update_submodules():
                logger.error("Failed to initialize submodules")
                return False
        return True

    def _execute_with_editor(self, container_config: ContainerConfig, build_environment) -> int:
        """Execute container with editor integration."""
        try:
            editor_strategy: EditorStrategy = self.di_container.get_editor_strategy(self.buildparam.editor_mode)

            ssh_port = editor_strategy.find_free_port()
            container_config.ports = {ssh_port: 22}
            container_config.detached = True

            container_config.command = ContainerUtils.build_ssh_enabled_command()

            ssh_keys_mount = f"{os.path.expanduser('~/.ssh')}:/tmp/ssh_keys:ro"
            container_config.volumes.append(ssh_keys_mount)

            if container_config.env_file:
                env_file_mount = f"{container_config.env_file}:/tmp/container_env:ro"
                container_config.volumes.append(env_file_mount)

            editor_config = EditorConfig(
                project_path=self.buildparam.project_dir, ssh_port=ssh_port, container_name=container_config.name
            )

            if not editor_strategy.setup_remote_connection(editor_config):
                logger.error("Failed to setup editor remote connection")
                return 1

            result = self.container_service.run_container(container_config)

            if result.return_code == 0:
                launch_result = editor_strategy.launch_editor(editor_config)

                if launch_result.success:
                    self.output.info(
                        "Container running in background\n"
                        "Container name: {}\n"
                        "SSH access: ssh root@localhost -p {}\n"
                        "Authentication: SSH key or password 'root'\n"
                        "Editor should open automatically\n\n"
                        "Build script available: {}\n\n"
                        "To stop the container: docker stop {}".format(
                            container_config.name,
                            ssh_port,
                            build_environment.full_script,
                            container_config.name
                        )
                    )
                else:
                    self.output.error(
                        "Editor launch failed: {}".format(launch_result.error_message),
                    )

            return result.return_code

        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Failed to execute with editor: %s", e)
            return 1

    def _build_container_config(self, build_environment, env_file) -> ContainerConfig:
        """Build container configuration from environment and BuildConfig."""
        sanitized_package = BuildUtils.sanitize_container_name(self.buildparam.package_name)
        sanitized_workspace = BuildUtils.sanitize_container_name(self.buildparam.branch)
        sanitized_arch = BuildUtils.sanitize_container_name(self.buildparam.architecture)
        container_name = f"{sanitized_package}-{sanitized_workspace}_{sanitized_arch}"

        volumes = [f"{os.getcwd()}:{self.buildparam.project_dir}"]
        if self.buildparam.mount:
            volumes.append(self.buildparam.mount)

        config = ContainerConfig(
            image=build_environment.image,
            name=container_name,
            command=build_environment.full_script,
            working_dir=self.buildparam.project_dir,
            environment={},
            volumes=volumes,
            network=self.buildparam.network,
            platform=self.buildparam.platform,
            interactive=self.buildparam.shell_mode,
            privileged=self.buildparam.privileged,
            remove_on_exit=not self.buildparam.editor_mode,
        )

        config.env_file = env_file.name

        if self.buildparam.shell_mode:
            config.command = "/usr/bin/bash"
            config.interactive = True
            self.output.print(f"Container name: {container_name}")
            self.output.print()
            self.output.warning("Run this to build the package:")
            self.output.success(build_environment.full_script)

        return config

    def _determine_project_dir(self, is_shell_mode: bool, is_editor_mode: bool = False) -> str:
        """Determine the project directory path based on shell or editor mode."""
        shell_project_dir = "/build"
        if is_shell_mode or is_editor_mode:
            return shell_project_dir
        return "/" + "".join(random.sample(shell_project_dir[1:], k=len(shell_project_dir[1:])))
