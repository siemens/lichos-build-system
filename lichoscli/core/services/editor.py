# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class EditorConfig:
    """Configuration for editor integration."""

    project_path: str
    ssh_port: Optional[int] = None
    ssh_config_path: Optional[str] = None
    container_name: Optional[str] = None


@dataclass
class EditorLaunchResult:
    """Result of editor launch operation."""

    success: bool
    process_id: Optional[int] = None
    error_message: Optional[str] = None


class EditorStrategy(ABC):
    """Abstract strategy interface for different editor integrations."""

    @abstractmethod
    def get_editor_name(self) -> str:
        """Get the name of this editor strategy."""

    @abstractmethod
    def setup_remote_connection(self, config: EditorConfig) -> bool:
        """
        Setup remote connection configuration for the editor.

        Args:
            config: Editor configuration including connection details

        Returns:
            True if setup successful, False otherwise
        """

    @abstractmethod
    def launch_editor(self, config: EditorConfig) -> EditorLaunchResult:
        """
        Launch the editor with remote connection to container.

        Args:
            config: Editor configuration

        Returns:
            EditorLaunchResult with launch details
        """

    @abstractmethod
    def wait_for_connection_ready(self, config: EditorConfig, timeout_seconds: int = 180) -> bool:
        """
        Wait for the remote connection to be ready.

        Args:
            config: Editor configuration
            timeout_seconds: Maximum time to wait for connection

        Returns:
            True if connection is ready, False if timeout or error
        """

    @abstractmethod
    def cleanup_connection(self, config: EditorConfig) -> None:
        """
        Clean up any temporary connection configuration.

        Args:
            config: Editor configuration to clean up
        """
