"""Coordinated GitLab issue writer for storage and notification services."""

import logging
import re
from typing import Optional

import gitlab

logger = logging.getLogger(__name__)


class GitLabIssueWriter:
    """
    Coordinated writer for GitLab issues that manages both storage data (as HTML comments)
    and notification content (as visible content) without overwriting each other.
    """

    def __init__(self, gitlab_client: gitlab.Gitlab, project_id: str):
        self.gitlab = gitlab_client
        self.project_id = project_id

    def read_issue_parts(self, issue_id: str) -> tuple[Optional[str], Optional[str]]:
        """
        Read both storage data and notification content from an issue.

        Args:
            issue_id: GitLab issue ID

        Returns:
            Tuple of (storage_data_json, notification_content) or (None, None) if issue not found
        """
        try:
            project = self.gitlab.projects.get(self.project_id)
            issue = project.issues.get(issue_id)

            if not issue:
                logger.warning("Issue %s not found", issue_id)
                return None, None

            description = getattr(issue, "description", "") or ""
            if not description:
                logger.debug("Issue %s has empty description", issue_id)
                return None, None

            storage_data = None
            match = re.search(r"<!--\s*SCHEDULER_DAG\s*\n(.*?)\n\s*-->", description, re.DOTALL)
            if match:
                storage_data = match.group(1).strip()

            notification_content = re.sub(
                r"<!--\s*SCHEDULER_DAG\s*\n.*?\n\s*-->", "", description, flags=re.DOTALL
            ).strip()

            return storage_data, notification_content if notification_content else None

        except gitlab.GitlabGetError as e:
            logger.warning("Issue %s not found: %s", issue_id, e)
            return None, None
        except gitlab.GitlabError as e:
            logger.error("GitLab error reading issue %s: %s", issue_id, e)
            return None, None

    def write_issue_parts(
        self,
        issue_id: str,
        storage_data_json: Optional[str] = None,
        notification_content: Optional[str] = None,
        preserve_existing: bool = True,
    ) -> bool:
        """
        Write storage data and/or notification content to an issue.

        Args:
            issue_id: GitLab issue ID
            storage_data_json: JSON data to store in HTML comment (None to keep existing)
            notification_content: Visible content for notifications (None to keep existing)
            preserve_existing: If True, preserve existing data when new data is None

        Returns:
            True if successfully written, False otherwise
        """
        try:
            project = self.gitlab.projects.get(self.project_id)
            issue = project.issues.get(issue_id)

            current_storage_data, current_notification_content = None, None
            if preserve_existing:
                current_storage_data, current_notification_content = self.read_issue_parts(issue_id)

            final_storage_data = storage_data_json if storage_data_json is not None else current_storage_data
            final_notification_content = (
                notification_content if notification_content is not None else current_notification_content
            )

            description_parts = []

            if final_storage_data:
                description_parts.append(f"<!-- SCHEDULER_DAG\n{final_storage_data}\n-->")

            if final_notification_content:
                description_parts.append(final_notification_content)

            new_description = "\n\n".join(description_parts)

            issue.description = new_description
            issue.save()

            logger.debug("Successfully updated issue %s", issue_id)
            return True

        except gitlab.GitlabGetError as e:
            logger.error("Issue %s not found for update: %s", issue_id, e)
            return False
        except gitlab.GitlabError as e:
            logger.error("GitLab error updating issue %s: %s", issue_id, e)
            return False

    def create_issue(self, title: str, description: str = "", labels: Optional[list] = None) -> str:
        """
        Create a new GitLab issue.

        Args:
            title: Title for the issue
            description: Optional description for the issue
            labels: Optional list of labels to add

        Returns:
            The issue ID as string
        """
        try:
            project = self.gitlab.projects.get(self.project_id)

            issue_data = {
                "title": title,
                "description": description or "Automated issue for scheduler state and notifications.",
                "labels": labels or ["scheduler", "automated"],
            }

            issue = project.issues.create(issue_data)
            issue_id = str(issue.iid)
            logger.info("Created issue %s with title: %s", issue_id, title)
            return issue_id

        except gitlab.GitlabError as e:
            logger.error("Failed to create issue: %s", e)
            raise

    def find_issue_by_title(self, title: str) -> Optional[str]:
        """
        Find a GitLab issue by its title.

        Args:
            title: Title to search for

        Returns:
            The issue ID as string if found, None otherwise
        """
        try:
            project = self.gitlab.projects.get(self.project_id)

            issues = project.issues.list(search=title, state="opened", all=True)

            for issue in issues:
                if issue.title == title:
                    logger.info("Found existing issue %s with title: %s", issue.iid, title)
                    return str(issue.iid)

            logger.debug("No issue found with title: %s", title)
            return None

        except gitlab.GitlabError as e:
            logger.error("Failed to search for issue with title '%s': %s", title, e)
            return None

    def get_issue_subscribers(self, issue_id: str) -> list[str]:
        """
        Get list of users subscribed to notifications via thumbs up emoji.

        Args:
            issue_id: GitLab issue ID

        Returns:
            List of usernames subscribed to notifications
        """
        try:
            project = self.gitlab.projects.get(self.project_id)
            issue = project.issues.get(issue_id)

            award_emojis = issue.awardemojis.list(all=True)

            subscribers = []
            for emoji in award_emojis:
                if emoji.name == "thumbsup":
                    subscribers.append(emoji.user["username"])

            return subscribers

        except gitlab.GitlabError as e:
            logger.error("Failed to get subscriber list for issue %s: %s", issue_id, e)
            return []
