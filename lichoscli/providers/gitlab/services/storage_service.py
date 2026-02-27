# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of storage service using issues for state persistence."""

import json
import logging
from typing import Optional

from lichoscli.core.models.dag import DependencyGraph
from lichoscli.core.services.storage import StorageService
from lichoscli.providers.gitlab.services.gitlab_issue_writer import GitLabIssueWriter

logger = logging.getLogger(__name__)


class GitLabStorageService(StorageService):
    """GitLab-based storage service that saves scheduler state to issue descriptions."""

    def __init__(self, issue_writer: GitLabIssueWriter):
        self.issue_writer = issue_writer

    def load_state(self, storage_id: str) -> Optional[DependencyGraph]:
        """
        Load scheduler DAG state from a GitLab issue description.

        Args:
            storage_id: GitLab issue ID

        Returns:
            The loaded dependency graph or None if not found
        """
        storage_data_json, _ = self.issue_writer.read_issue_parts(storage_id)

        if not storage_data_json:
            logger.debug("No scheduler DAG found in issue %s", storage_id)
            return None

        try:
            dag_dict = json.loads(storage_data_json)
            return DependencyGraph.from_dict(dag_dict)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse scheduler DAG JSON from issue %s: %s", storage_id, e)
            return None

    def save_state(self, storage_id: str, dag: DependencyGraph) -> bool:
        """
        Save scheduler DAG state to a GitLab issue description.

        Args:
            storage_id: GitLab issue ID
            dag: The dependency graph to save

        Returns:
            True if successfully saved, False otherwise
        """
        dag_json = json.dumps(dag.to_dict(), indent=2)
        success = self.issue_writer.write_issue_parts(storage_id, storage_data_json=dag_json, preserve_existing=True)

        if success:
            logger.debug("Successfully saved scheduler DAG to issue %s", storage_id)
        else:
            logger.error("Failed to save scheduler DAG to issue %s", storage_id)

        return success

    def create_storage(self, title: str, description: str = "") -> str:
        """
        Create a new GitLab issue to store scheduler state.

        Args:
            title: Title for the issue
            description: Optional description for the issue

        Returns:
            The issue ID as string
        """
        final_description = description or "Scheduler state storage issue created automatically."
        issue_id = self.issue_writer.create_issue(title, final_description, labels=["scheduler", "automated"])
        logger.info("Created storage issue %s with title: %s", issue_id, title)
        return issue_id

    def find_storage_by_title(self, title: str) -> Optional[str]:
        """
        Find a GitLab issue by its title for storage.

        Args:
            title: Title to search for

        Returns:
            The issue ID as string if found, None otherwise
        """
        issue_id = self.issue_writer.find_issue_by_title(title)
        if issue_id:
            logger.info("Found existing storage issue %s with title: %s", issue_id, title)
        else:
            logger.debug("No storage issue found with title: %s", title)
        return issue_id
