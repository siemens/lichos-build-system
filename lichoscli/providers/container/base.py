# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Shared OCI container runtime base class.

Both ``DockerContainerService`` and ``PodmanContainerService`` derive from this.
Subclasses only describe how the runtime-specific ``run`` command is built; every
other operation (``pull``, ``stop``, ``remove``, ``exists``, ``logs``,
``is_running``) follows the same docker-compatible CLI surface.
"""

from __future__ import annotations

import logging
import subprocess
from abc import abstractmethod

from lichoscli.core.services import ContainerConfig, ContainerResult, ContainerService

logger = logging.getLogger(__name__)


class OciContainerService(ContainerService):
    """Common implementation for docker-compatible container CLIs."""

    def __init__(self, command: str):
        self._command = command

    @property
    def command(self) -> str:
        """The executable name used to invoke the runtime."""
        return self._command

    def pull_image(self, image: str) -> int:
        """Pull a container image."""
        try:
            logger.info("Pulling image %s with %s", image, self._command)
            result = subprocess.run([self._command, "pull", image], check=False)

            if result.returncode != 0:
                logger.error("Failed to pull image %s", image)
            else:
                logger.info("Successfully pulled image: %s", image)

            return result.returncode

        except subprocess.SubprocessError as e:
            logger.error("Error pulling image %s: %s", image, e)
            return 1

    def run_container(self, config: ContainerConfig) -> ContainerResult:
        """Run a container with the given configuration."""
        try:
            if self.container_exists(config.name):
                logger.info("Removing existing container: %s", config.name)
                self.stop_container(config.name)
                self.remove_container(config.name)

            cmd = self.build_run_command(config)

            logger.info("Running container with command: %s", " ".join(cmd))
            result = subprocess.run(cmd, check=False)

            return ContainerResult(return_code=result.returncode, container_name=config.name)

        except subprocess.SubprocessError as e:
            logger.error("Error running container %s: %s", config.name, e)
            return ContainerResult(return_code=1)

    def stop_container(self, container_name: str) -> bool:
        """Stop a running container."""
        try:
            result = subprocess.run(
                [self._command, "stop", container_name],
                capture_output=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info("Successfully stopped container: %s", container_name)
                return True

            logger.warning(
                "Failed to stop container %s: %s",
                container_name,
                result.stderr.decode(errors="replace") if result.stderr else "",
            )
            return False

        except subprocess.SubprocessError as e:
            logger.error("Error stopping container %s: %s", container_name, e)
            return False

    def remove_container(self, container_name: str) -> bool:
        """Remove a container."""
        try:
            result = subprocess.run(
                [self._command, "rm", container_name],
                capture_output=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info("Successfully removed container: %s", container_name)
                return True

            logger.warning(
                "Failed to remove container %s: %s",
                container_name,
                result.stderr.decode(errors="replace") if result.stderr else "",
            )
            return False

        except subprocess.SubprocessError as e:
            logger.error("Error removing container %s: %s", container_name, e)
            return False

    def container_exists(self, container_name: str) -> bool:
        """Check if a container exists."""
        try:
            result = subprocess.run(
                [self._command, "ps", "-aq", "-f", f"name={container_name}"],
                capture_output=True,
                text=True,
                check=False,
            )

            return bool(result.stdout.strip())

        except subprocess.SubprocessError as e:
            logger.error("Error checking if container exists %s: %s", container_name, e)
            return False

    def get_container_logs(self, container_name: str, tail_lines: int = 50) -> str:
        """Get logs from a container."""
        try:
            result = subprocess.run(
                [self._command, "logs", "--tail", str(tail_lines), container_name],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return result.stdout + result.stderr

            logger.warning("Failed to get logs from container %s", container_name)
            return ""

        except subprocess.SubprocessError as e:
            logger.error("Error getting logs from container %s: %s", container_name, e)
            return ""

    def is_container_running(self, container_name: str) -> bool:
        """Check if a container is currently running."""
        try:
            result = subprocess.run(
                [self._command, "ps", "-q", "-f", f"name={container_name}"],
                capture_output=True,
                text=True,
                check=False,
            )

            return bool(result.stdout.strip())

        except subprocess.SubprocessError as e:
            logger.error("Error checking if container is running %s: %s", container_name, e)
            return False

    @abstractmethod
    def build_run_command(self, config: ContainerConfig) -> list[str]:
        """Build the runtime-specific ``run`` command from configuration.

        Implementations should typically start from ``self.compose_run_command``
        and prepend any runtime-specific options (uid mapping, etc.).
        """

    def compose_run_command(self, config: ContainerConfig, runtime_options: list[str] | None = None) -> list[str]:
        """Compose the final runtime ``run`` command from shared and runtime-specific options.

        Subclasses call this with their runtime-specific flags (e.g. podman's
        ``--uidmap``). The returned list is a full command suitable for
        ``subprocess.run``.
        """
        runtime_options = runtime_options or []
        cmd = [self._command, "run", "--name", config.name]
        cmd.extend(runtime_options)

        if config.env_file:
            cmd.extend(["--env-file", config.env_file])

        for key, value in config.environment.items():
            cmd.extend(["-e", f"{key}={value}"])

        for volume in config.volumes:
            cmd.extend(["-v", volume])

        for host_port, container_port in config.ports.items():
            cmd.extend(["-p", f"{host_port}:{container_port}"])

        if config.network:
            cmd.extend(["--network", config.network])

        if config.platform:
            cmd.extend(["--platform", config.platform])

        if config.working_dir:
            cmd.extend(["-w", config.working_dir])

        if config.detached:
            cmd.append("-d")
        if config.interactive:
            cmd.append("-it")
        if config.privileged:
            cmd.append("--privileged")
        if config.remove_on_exit and not config.detached:
            cmd.append("--rm")

        cmd.append(config.image)

        if config.command:
            cmd.extend(["/bin/bash", "-c", config.command])

        return cmd
