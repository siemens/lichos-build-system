# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Filesystem implementation of notification service for local console output."""

import logging
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from lichoscli.core.models.dag import DAGNodeStatus
from lichoscli.core.services.notify import NotificationData, NotifyService

logger = logging.getLogger(__name__)


class FilesystemNotifyService(NotifyService):
    """Filesystem-based notification service that outputs to console/logs instead of remote systems."""

    def __init__(self):
        """Initialize the filesystem notification service with a Rich console."""
        self.console = Console()

    def send_notification(self, notification_id: str, data: NotificationData) -> bool:
        """
        Send a notification using Rich console formatting.

        Args:
            notification_id: Identifier for the notification (used as title)
            data: Notification data containing build results

        Returns:
            True (always succeeds for console output)
        """
        self.console.print()

        title = f"🔔 SCHEDULER NOTIFICATION - {notification_id}"
        panel = Panel(
            self._format_notification_content(data),
            title=title,
            title_align="left",
            border_style="bright_blue",
            padding=(1, 2),
        )

        self.console.print(panel)
        self.console.print()
        return True

    def _format_notification_content(self, data: NotificationData) -> str:
        """Format the notification content using Rich markup."""
        content_parts = []

        actual_failed_packages = set(data.failed_packages)
        for pkg_name, dag_node in data.dag_nodes.items():
            if dag_node.status == DAGNodeStatus.FAILED:
                actual_failed_packages.add(pkg_name)

        if actual_failed_packages:
            content_parts.append("[bold red]❌ FAILED PACKAGES:[/bold red]")
            for pkg_name in actual_failed_packages:
                dag_node = data.dag_nodes.get(pkg_name)
                status = dag_node.status.value if dag_node and dag_node.status else "failed"
                pipeline_url = data.pipeline_urls.get(pkg_name, "N/A")
                content_parts.append(
                    f"  • [red]{pkg_name}[/red] ([dim]{status}[/dim]) - Pipeline: {pipeline_url}"
                )

        if data.package_comparison_urls:
            if content_parts:
                content_parts.append("")
            content_parts.append("[bold yellow]📊 PACKAGES WITH CHANGES:[/bold yellow]")
            for pkg_name, url in data.package_comparison_urls.items():
                content_parts.append(f"  • [yellow]{pkg_name}[/yellow]: {url}")

        if not actual_failed_packages and not data.successful_packages:
            content_parts.append("[dim]ℹ️  No package status information available[/dim]")

        return "\n".join(content_parts)

    def get_subscriber_list(self, notification_id: str) -> list[str]:
        """
        Get list of users subscribed to notifications.

        Args:
            notification_id: Identifier for the notification target

        Returns:
            Empty list (no subscribers for filesystem notifications)
        """
        return []

    def create_notification_target(self, title: str, description: str = "") -> str:
        """
        Create a new notification target.

        Args:
            title: Title for the notification target
            description: Optional description

        Returns:
            A simple identifier based on the title
        """
        notification_id = title.lower().replace(" ", "-").replace("/", "-")
        logger.debug("Created filesystem notification target: %s", notification_id)
        return notification_id

    def find_notification_target_by_title(self, title: str) -> Optional[str]:
        """
        Find a notification target by its title.

        Args:
            title: Title to search for

        Returns:
            A simple identifier based on the title (always succeeds for filesystem)
        """
        # For filesystem, we can always "find" a target by creating the ID from title
        return title.lower().replace(" ", "-").replace("/", "-")
