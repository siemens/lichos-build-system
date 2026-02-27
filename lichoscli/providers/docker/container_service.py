# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import subprocess

from lichoscli.core.services import ContainerConfig, ContainerResult, ContainerService

logger = logging.getLogger(__name__)


class DockerContainerService(ContainerService):
    """Docker implementation of ContainerService."""

    def pull_image(self, image: str) -> int:
        """Pull a Docker image."""
        try:
            logger.info("Pulling Docker image: %s", image)
            result = subprocess.run(["docker", "pull", image], check=False)

            if result.returncode != 0:
                logger.error("Failed to pull image %s", image)
            else:
                logger.info("Successfully pulled image: %s", image)

            return result.returncode

        except subprocess.SubprocessError as e:
            logger.error("Error pulling Docker image %s: %s", image, e)
            return 1

    def run_container(self, config: ContainerConfig) -> ContainerResult:
        """Run a Docker container with the given configuration."""
        try:
            if self.container_exists(config.name):
                logger.info("Removing existing container: %s", config.name)
                self.stop_container(config.name)
                self.remove_container(config.name)

            cmd = self._build_docker_command(config)

            logger.info("Running Docker container with command: %s", " ".join(cmd))
            result = subprocess.run(cmd, check=False)

            return ContainerResult(return_code=result.returncode, container_name=config.name)

        except subprocess.SubprocessError as e:
            logger.error("Error running Docker container %s: %s", config.name, e)
            return ContainerResult(return_code=1)

    def stop_container(self, container_name: str) -> bool:
        """Stop a running Docker container."""
        try:
            result = subprocess.run(["docker", "stop", container_name], capture_output=True, check=False)

            if result.returncode == 0:
                logger.info("Successfully stopped container: %s", container_name)
                return True
            else:
                logger.warning("Failed to stop container %s: %s", container_name, result.stderr.decode())
                return False

        except subprocess.SubprocessError as e:
            logger.error("Error stopping container %s: %s", container_name, e)
            return False

    def remove_container(self, container_name: str) -> bool:
        """Remove a Docker container."""
        try:
            result = subprocess.run(["docker", "rm", container_name], capture_output=True, check=False)

            if result.returncode == 0:
                logger.info("Successfully removed container: %s", container_name)
                return True
            else:
                logger.warning("Failed to remove container %s: %s", container_name, result.stderr.decode())
                return False

        except subprocess.SubprocessError as e:
            logger.error("Error removing container %s: %s", container_name, e)
            return False

    def container_exists(self, container_name: str) -> bool:
        """Check if a Docker container exists."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-aq", "-f", f"name={container_name}"], capture_output=True, text=True, check=False
            )

            return bool(result.stdout.strip())

        except subprocess.SubprocessError as e:
            logger.error("Error checking if container exists %s: %s", container_name, e)
            return False

    def get_container_logs(self, container_name: str, tail_lines: int = 50) -> str:
        """Get logs from a Docker container."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail_lines), container_name],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return result.stdout + result.stderr
            else:
                logger.warning("Failed to get logs from container %s", container_name)
                return ""

        except subprocess.SubprocessError as e:
            logger.error("Error getting logs from container %s: %s", container_name, e)
            return ""

    def is_container_running(self, container_name: str) -> bool:
        """Check if a Docker container is currently running."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={container_name}"], capture_output=True, text=True, check=False
            )

            return bool(result.stdout.strip())

        except subprocess.SubprocessError as e:
            logger.error("Error checking if container is running %s: %s", container_name, e)
            return False

    def _build_docker_command(self, config: ContainerConfig) -> list[str]:
        """Build the Docker command from configuration."""
        cmd = ["docker", "run", "--name", config.name]

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
