# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ContainerConfig:
    """Configuration for container execution."""

    image: str
    name: str
    command: str
    working_dir: str
    environment: dict[str, str] = None
    volumes: list[str] = None
    ports: dict[int, int] = None
    network: Optional[str] = None
    platform: Optional[str] = None
    detached: bool = False
    interactive: bool = False
    remove_on_exit: bool = True
    privileged: bool = False
    env_file: Optional[str] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.volumes is None:
            self.volumes = []
        if self.ports is None:
            self.ports = {}


@dataclass
class ContainerResult:
    """Result of container execution."""

    return_code: int
    container_id: Optional[str] = None
    container_name: Optional[str] = None


class ContainerService(ABC):
    """Abstract interface for container management operations."""

    @abstractmethod
    def pull_image(self, image: str) -> int:
        """
        Pull a container image.

        Args:
            image: Image name to pull

        Returns:
            0 on success, non-zero on failure
        """

    @abstractmethod
    def run_container(self, config: ContainerConfig) -> ContainerResult:
        """
        Run a container with the given configuration.

        Args:
            config: Container configuration

        Returns:
            ContainerResult with execution details
        """

    @abstractmethod
    def stop_container(self, container_name: str) -> bool:
        """
        Stop a running container.

        Args:
            container_name: Name of container to stop

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def remove_container(self, container_name: str) -> bool:
        """
        Remove a container.

        Args:
            container_name: Name of container to remove

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def container_exists(self, container_name: str) -> bool:
        """
        Check if a container exists.

        Args:
            container_name: Name of container to check

        Returns:
            True if container exists, False otherwise
        """

    @abstractmethod
    def get_container_logs(self, container_name: str, tail_lines: int = 50) -> str:
        """
        Get logs from a container.

        Args:
            container_name: Name of container
            tail_lines: Number of lines to retrieve from end

        Returns:
            Container logs as string
        """

    @abstractmethod
    def is_container_running(self, container_name: str) -> bool:
        """
        Check if a container is currently running.

        Args:
            container_name: Name of container to check

        Returns:
            True if container is running, False otherwise
        """
