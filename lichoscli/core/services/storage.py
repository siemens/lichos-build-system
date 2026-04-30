# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract storage service interface for scheduler state persistence."""

from abc import ABC, abstractmethod
from typing import Optional

from lichoscli.core.models.dag import DependencyGraph
from lichoscli.utils.constants import SCHEDULER_REPORT_TITLE


class StorageService(ABC):
    """Abstract interface for persisting scheduler state."""

    @abstractmethod
    def load_state(self, storage_id: str) -> Optional[DependencyGraph]:
        """
        Load scheduler DAG state from persistent storage.

        Args:
            storage_id: Identifier for the storage location (e.g., issue ID, file path)

        Returns:
            The loaded dependency graph or None if not found
        """
        raise NotImplementedError

    @abstractmethod
    def save_state(self, storage_id: str, dag: DependencyGraph) -> bool:
        """
        Save scheduler DAG state to persistent storage.

        Args:
            storage_id: Identifier for the storage location
            dag: The dependency graph to save

        Returns:
            True if successfully saved, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def create_storage(self, title: str, description: str = "") -> str:
        """
        Create a new storage location for scheduler state.

        Args:
            title: Title for the storage location
            description: Optional description

        Returns:
            The storage identifier for the created location
        """
        raise NotImplementedError

    @abstractmethod
    def find_storage_by_title(self, title: str) -> Optional[str]:
        """
        Find a storage location by its title.

        Args:
            title: Title to search for

        Returns:
            The storage identifier if found, None otherwise
        """
        raise NotImplementedError

    def load_workspace_state(self, workspace_name: str) -> Optional[DependencyGraph]:
        """
        Load scheduler DAG state for a workspace, handling storage target creation automatically.
        Returns the most recent scheduler run state.

        Args:
            workspace_name: Name of the workspace

        Returns:
            The loaded dependency graph or None if not found
        """
        try:
            title = SCHEDULER_REPORT_TITLE.format(workspace_name)
            storage_id = self.find_storage_by_title(title)

            if not storage_id:
                return None

            return self.load_state(storage_id)
        except (OSError, ValueError):
            return None

    def save_workspace_state(self, workspace_name: str, dag: DependencyGraph) -> bool:
        """
        Save scheduler DAG state for a workspace, creating storage target if needed.
        Each run creates a new timestamped entry to maintain history.

        Args:
            workspace_name: Name of the workspace
            dag: The dependency graph to save

        Returns:
            True if successfully saved, False otherwise
        """
        try:
            title = SCHEDULER_REPORT_TITLE.format(workspace_name)

            storage_id = self.find_storage_by_title(title)

            if not storage_id:
                description = "Automated scheduler DAG state storage for workspace '{0}'".format(workspace_name)
                storage_id = self.create_storage(title, description)

            return self.save_state(storage_id, dag)
        except (OSError, ValueError):
            return False


class NoOpStorageService(StorageService):
    """No-op storage service for local runs where state persistence is not needed."""

    def load_state(self, storage_id: str) -> Optional[DependencyGraph]:
        return None

    def save_state(self, storage_id: str, dag: DependencyGraph) -> bool:
        return True

    def create_storage(self, title: str, description: str = "") -> str:
        return title

    def find_storage_by_title(self, title: str) -> Optional[str]:
        return None
