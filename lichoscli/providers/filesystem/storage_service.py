# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Filesystem implementation of storage service for local state persistence."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from xdg import xdg_data_home

from lichoscli.core.models.dag import DependencyGraph
from lichoscli.core.services.storage import StorageService

logger = logging.getLogger(__name__)


class FilesystemStorageService(StorageService):
    """Filesystem-based storage service that saves scheduler state to JSON files."""

    def __init__(self, base_dir: str = None):
        """
        Initialize filesystem storage service.

        Args:
            base_dir: Base directory for storing state files. Defaults to XDG data directory
        """
        if base_dir is None:
            base_dir = xdg_data_home() / "lichoscli"

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Initialized filesystem storage at %s", self.base_dir)

    def load_state(self, storage_id: str) -> Optional[DependencyGraph]:
        """
        Load most recent scheduler DAG state from timestamped files.
        Loads from directory structure: .lichos/<workspace>/scheduler_runs/

        Args:
            storage_id: Workspace identifier (workspace name)

        Returns:
            The loaded dependency graph or None if not found
        """
        try:
            workspace_dir = self.base_dir / storage_id / "scheduler_runs"

            if not workspace_dir.exists():
                logger.debug("Scheduler runs directory %s does not exist", workspace_dir)
                return None

            run_files = sorted(workspace_dir.glob("scheduler_run_*.json"), reverse=True)
            if not run_files:
                logger.debug("No scheduler run files found in %s", workspace_dir)
                return None

            latest_file = run_files[0]
            logger.debug("Loading latest scheduler run from %s", latest_file)

            with open(latest_file, encoding="utf-8") as f:
                dag_dict = json.load(f)
                return DependencyGraph.from_dict(dag_dict)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Failed to parse scheduler DAG from %s: %s", latest_file, e)
            return None
        except OSError as e:
            logger.error("Failed to read scheduler DAG from %s: %s", workspace_dir, e)
            return None

    def save_state(self, storage_id: str, dag: DependencyGraph) -> bool:
        """
        Save scheduler DAG state to timestamped JSON files for history tracking.
        Creates directory structure: .lichos/<workspace>/scheduler_runs/

        Args:
            storage_id: Workspace identifier (workspace name)
            dag: The dependency graph to save

        Returns:
            True if successfully saved, False otherwise
        """
        try:
            workspace_dir = self.base_dir / storage_id / "scheduler_runs"
            workspace_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = workspace_dir / f"scheduler_run_{timestamp}.json"

            dag_dict = dag.to_dict()

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(dag_dict, f, indent=2, ensure_ascii=False)

            logger.debug("Successfully saved scheduler DAG to %s", file_path)
            return True

        except OSError as e:
            logger.error("Failed to save scheduler DAG to %s: %s", file_path, e)
            return False
        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize scheduler DAG: %s", e)
            return False

    def create_storage(self, title: str, description: str = "") -> str:
        """
        Create a new storage identifier for scheduler state.
        Extracts workspace name from title and creates directory structure.

        Args:
            title: Title for the storage, format: "Scheduler Report for <workspace>"
            description: Optional description (ignored for filesystem)

        Returns:
            The storage identifier (workspace name)
        """
        try:
            if title.startswith("Scheduler Report for "):
                workspace_name = title[len("Scheduler Report for ") :]
            else:
                workspace_name = self._sanitize_filename(title)

            workspace_dir = self.base_dir / workspace_name / "scheduler_runs"
            workspace_dir.mkdir(parents=True, exist_ok=True)

            logger.info("Created storage directory %s for workspace: %s", workspace_dir, workspace_name)
            return workspace_name

        except RuntimeError as e:
            logger.error("Failed to create storage: %s", e)
            raise

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize a string to be used as a filename."""
        invalid_chars = '<>:"/\\|?*'
        sanitized = filename
        for char in invalid_chars:
            sanitized = sanitized.replace(char, "_")

        sanitized = sanitized.strip(" .")

        if not sanitized:
            sanitized = "scheduler_storage"

        if len(sanitized) > 100:
            sanitized = sanitized[:100]

        return sanitized

    def list_storage_files(self) -> list[str]:
        """List all available workspaces with scheduler runs."""
        try:
            workspaces = []
            for workspace_dir in self.base_dir.iterdir():
                if workspace_dir.is_dir():
                    scheduler_runs_dir = workspace_dir / "scheduler_runs"
                    if scheduler_runs_dir.exists() and any(scheduler_runs_dir.glob("scheduler_run_*.json")):
                        workspaces.append(workspace_dir.name)
            return workspaces
        except OSError as e:
            logger.error("Failed to list storage workspaces: %s", e)
            return []

    def find_storage_by_title(self, title: str) -> Optional[str]:
        """
        Find a storage location by its title by checking workspace directories.
        Extracts workspace name from title "Scheduler Report for <workspace>".

        Args:
            title: Title to search for

        Returns:
            The storage identifier (workspace name) if found, None otherwise
        """
        try:
            if title.startswith("Scheduler Report for "):
                workspace_name = title[len("Scheduler Report for ") :]
                workspace_dir = self.base_dir / workspace_name / "scheduler_runs"

                if workspace_dir.exists() and any(workspace_dir.glob("scheduler_run_*.json")):
                    logger.info("Found existing scheduler runs for workspace: %s", workspace_name)
                    return workspace_name

            logger.debug("No scheduler runs found for title: %s", title)
            return None

        except OSError as e:
            logger.error("Failed to search for storage with title '%s': %s", title, e)
            return None
