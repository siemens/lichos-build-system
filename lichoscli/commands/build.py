import logging
import os
import random
import subprocess

from rich.panel import Panel

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models import BuildParameters
from lichoscli.core.services import (
    ContainerConfig,
    ContainerService,
    EditorConfig,
    EnvironmentService,
    PackageService,
)
from lichoscli.core.services.editor import EditorStrategy
from lichoscli.utils import BuildUtils, ContainerUtils, GitUtils, ProgressUtils

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
        sp.add_argument("--network", nargs="?", help="docker network to use for the container")
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

    def _create_build_config(self, args) -> BuildParameters:
        """Create BuildConfig from command arguments."""
        package_name = BuildUtils.get_package_name(args.package)
        branch = BuildUtils.get_branch_name(args.branch)
        architecture = BuildUtils.normalize_architecture(args.architecture)
        project_dir = self._determine_project_dir(args.shell, args.editor)
        group = args.pkg_group or GitUtils.get_group()
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
            custom_script=args.script,
            platform=platform,
        )

    def execute(self):
        if not self.package:
            logger.error("Package '%s' not found", self.buildparam.package_name)
            return 1

        self.console.print(f"Building package: [bold cyan]{self.package.name}[/bold cyan]")
        self.console.print(f"Architecture: [bold cyan]{self.buildparam.architecture}[/bold cyan]")

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

            env_file = self.environment_service.create_environment_file(build_environment.variables)
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
        repo = GitUtils.get_git_repo()
        if repo and GitUtils.has_submodules(repo):
            print("Submodules detected, initializing...")
            if not GitUtils.initialize_submodules(repo):
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
                    content_lines = [
                        f"Container name: [cyan]{container_config.name}[/cyan]",
                        f"SSH access: [cyan]ssh root@localhost -p {ssh_port}[/cyan]",
                        "Authentication: SSH key or password '[yellow]root[/yellow]'",
                        "Editor should open automatically",
                        "",
                        f"Build script available: [green]{build_environment.full_script}[/green]",
                        "",
                        "To stop the container:",
                        f"  [cyan]docker stop {container_config.name}[/cyan]",
                    ]

                    panel = Panel(
                        "\n".join(content_lines),
                        title="[bold green]CONTAINER RUNNING IN BACKGROUND[/bold green]",
                        border_style="green",
                        padding=(1, 2),
                    )
                    self.console.print()
                    self.console.print(panel)
                else:
                    self.console.print(f"[red]✗[/red] Editor launch failed: {launch_result.error_message}")

            return result.return_code

        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Failed to execute with editor: %s", e)
            return 1

    def _build_container_config(self, build_environment, env_file) -> ContainerConfig:
        """Build container configuration from environment and BuildConfig."""
        sanitized_package = BuildUtils.sanitize_container_name(self.buildparam.package_name)
        sanitized_workspace = BuildUtils.sanitize_container_name(self.buildparam.branch)
        container_name = f"devcontainer-{sanitized_package}-{sanitized_workspace}"

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
            remove_on_exit=not self.buildparam.editor_mode,
        )

        config.env_file = env_file.name

        if self.buildparam.shell_mode:
            config.command = "/usr/bin/bash"
            config.interactive = True
            self.console.print(f"Container name: [cyan]{container_name}[/cyan]")

            self.console.print()
            self.console.print("[bold yellow]RUN THIS TO BUILD THE PACKAGE:[/bold yellow]")
            self.console.print(f"[green]{build_environment.full_script}[/green]")
            self.console.print()

        return config

    def _determine_project_dir(self, is_shell_mode: bool, is_editor_mode: bool = False) -> str:
        """Determine the project directory path based on shell or editor mode."""
        shell_project_dir = "/build"
        if is_shell_mode or is_editor_mode:
            return shell_project_dir
        return "/" + "".join(random.sample(shell_project_dir[1:], k=len(shell_project_dir[1:])))
