"""GitLab implementation of notification service using issues for notifications."""

import json
import logging
from datetime import datetime
from typing import List, Optional

from lichoscli.core.models.dag import DAGNodeStatus
from lichoscli.core.services.notify import NotificationData, NotifyService
from lichoscli.providers.gitlab.services.gitlab_issue_writer import GitLabIssueWriter

logger = logging.getLogger(__name__)


class GitLabNotifyService(NotifyService):
    """GitLab-based notification service that sends notifications via issue updates."""

    def __init__(self, issue_writer: GitLabIssueWriter):
        self.issue_writer = issue_writer

    def send_notification(self, notification_id: str, data: NotificationData) -> bool:
        """
        Send a notification by updating a GitLab issue.

        Args:
            notification_id: GitLab issue ID
            data: Notification data containing build results

        Returns:
            True if notification was sent successfully, False otherwise
        """
        notification_lines = self._build_notification_content(data)

        subscribers = self.get_subscriber_list(notification_id)

        actual_failed_packages = set(data.failed_packages)
        for pkg_name, dag_node in data.dag_nodes.items():
            if dag_node.status == DAGNodeStatus.FAILED:
                actual_failed_packages.add(pkg_name)

        if actual_failed_packages and subscribers:
            notification_lines.append("")
            mentions = " ".join(f"@{user}" for user in subscribers)
            notification_lines.append(mentions)

        notification_lines.append("")
        notification_lines.append(
            "🔔 Would you like to be notified when package pipelines fail? "
            "Then give this issue a 👍. If you no longer wish to be notified, remove your 👍."
        )

        notification_body = "\n".join(notification_lines)

        success = self.issue_writer.write_issue_parts(
            notification_id, notification_content=notification_body, preserve_existing=True
        )

        if success:
            logger.info("Successfully sent notification to issue %s", notification_id)
        else:
            logger.error("Failed to send notification to issue %s", notification_id)

        return success

    def get_subscriber_list(self, notification_id: str) -> List[str]:
        """
        Get list of users subscribed to notifications via thumbs up emoji.

        Args:
            notification_id: GitLab issue ID

        Returns:
            List of usernames subscribed to notifications
        """
        return self.issue_writer.get_issue_subscribers(notification_id)

    def create_notification_target(self, title: str, description: str = "") -> str:
        """
        Create a new GitLab issue for notifications.

        Args:
            title: Title for the issue
            description: Optional description for the issue

        Returns:
            The issue ID as string
        """
        final_description = description or "Notification issue created automatically for scheduler alerts."
        issue_id = self.issue_writer.create_issue(
            title, final_description, labels=["notifications", "scheduler", "automated"]
        )
        logger.info("Created notification issue %s with title: %s", issue_id, title)
        return issue_id

    def _build_notification_content(self, notification: NotificationData) -> List[str]:
        """Build the notification content for the issue."""
        lines = []

        actual_failed_packages = set(notification.failed_packages)
        for pkg_name, dag_node in notification.dag_nodes.items():
            if dag_node.status == DAGNodeStatus.FAILED:
                actual_failed_packages.add(pkg_name)

        if notification.failed_packages or notification.successful_packages or notification.dag_nodes:
            pkg_list = {}

            for pkg_name, dag_node in notification.dag_nodes.items():
                pipeline_url = notification.pipeline_urls.get(pkg_name, "")

                actual_status = dag_node.status.value if dag_node.status else "unknown"
                pkg_list[pkg_name] = {"status": actual_status, "pipeline_url": pipeline_url}

            issue_data = {
                "pkg_list": pkg_list,
                "failed_packages": list(actual_failed_packages),
                "last_updated": datetime.now().isoformat(),
            }

            lines.append("<!--")
            lines.append(json.dumps(issue_data, indent=2))
            lines.append("-->")

        if not notification.failed_packages and not notification.successful_packages and not notification.dag_nodes:
            lines.append("📊 **Scheduler Run Report**")
            lines.append("")
            lines.append("No packages were processed in this run.")
            lines.append("")
            lines.append("🤖 _Automatic report by lichoscli scheduler_")
            return lines

        if actual_failed_packages:
            lines.append("❌ There are errors in the following pipelines:")
            lines.append("| Package | Status | Pipeline |")
            lines.append("|---------|--------|----------|")

            for pkg_name in actual_failed_packages:
                dag_node = notification.dag_nodes.get(pkg_name)
                status = dag_node.status.value if dag_node and dag_node.status else "failed"
                pipeline_url = notification.pipeline_urls.get(pkg_name, "N/A")

                if pipeline_url != "N/A":
                    pipeline_link = f"[🔗 Pipeline]({pipeline_url})"
                else:
                    pipeline_link = "N/A"

                lines.append(f"| {pkg_name} | {status} | {pipeline_link} |")

            if notification.package_comparison_urls:
                lines.append("")
                lines.append("### Package Changes")
                lines.append(f"**{len(notification.package_comparison_urls)} packages with changed commits:**")
                lines.append("")
                for pkg_name, url in notification.package_comparison_urls.items():
                    lines.append(f"- **{pkg_name}**: [🔗 Compare Commits]({url})")
                    logger.info("Added package comparison URL for %s: %s", pkg_name, url)

        else:
            lines.append("✅ Everything is ok, no pipelines are faulty 🥳")

        lines.append("")
        lines.append("🤖 _Automatic report by lichoscli scheduler_")

        return lines

    def find_notification_target_by_title(self, title: str) -> Optional[str]:
        """
        Find a GitLab issue by its title.

        Args:
            title: Title to search for

        Returns:
            The issue ID as string if found, None otherwise
        """
        issue_id = self.issue_writer.find_issue_by_title(title)
        if issue_id:
            logger.info("Found existing notification issue %s with title: %s", issue_id, title)
        else:
            logger.debug("No notification issue found with title: %s", title)
        return issue_id
