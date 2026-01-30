"""Abstract notification service interface for scheduler notifications."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from lichoscli.core.models.dag import DAGNode, DependencyGraph, DAGNodeStatus


class NotificationData:
    """Data for scheduler notifications."""

    def __init__(
        self,
        failed_packages: list[str],
        successful_packages: list[str],
        dag_nodes: Optional[dict[str, "DAGNode"]] = None,
        pipeline_urls: Optional[dict[str, str]] = None,
        package_comparison_urls: Optional[dict[str, str]] = None,
    ):
        self.failed_packages = failed_packages
        self.successful_packages = successful_packages
        self.dag_nodes = dag_nodes or {}
        self.pipeline_urls = pipeline_urls or {}
        self.package_comparison_urls = package_comparison_urls or {}


class NotifyService(ABC):
    """Abstract interface for sending scheduler notifications."""

    @abstractmethod
    def send_notification(self, notification_id: str, data: NotificationData) -> bool:
        """
        Send a notification about scheduler results.

        Args:
            notification_id: Identifier for the notification target (e.g., issue ID, channel)
            data: Notification data containing build results

        Returns:
            True if notification was sent successfully, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def get_subscriber_list(self, notification_id: str) -> list[str]:
        """
        Get list of users subscribed to notifications.

        Args:
            notification_id: Identifier for the notification target

        Returns:
            List of usernames subscribed to notifications
        """
        raise NotImplementedError

    @abstractmethod
    def create_notification_target(self, title: str, description: str = "") -> str:
        """
        Create a new notification target.

        Args:
            title: Title for the notification target
            description: Optional description

        Returns:
            The notification identifier for the created target
        """
        raise NotImplementedError

    @abstractmethod
    def find_notification_target_by_title(self, title: str) -> Optional[str]:
        """
        Find a notification target by its title.

        Args:
            title: Title to search for

        Returns:
            The notification identifier if found, None otherwise
        """
        raise NotImplementedError

    def create_notification(self, dag: "DependencyGraph", branch: str) -> NotificationData:
        from lichoscli.core.models.dag import DAGNodeStatus

        pipeline_urls = {}
        for package_name, node in dag.nodes.items():
            if node.project:
                pipeline = node.project.pipelines.get_latest(branch, use_cache=False)
                pipeline_urls[package_name] = pipeline.web_url if pipeline else "N/A"

        failed_nodes = dag.get_nodes_by_status(DAGNodeStatus.FAILED)
        successful_nodes = dag.get_nodes_by_status(DAGNodeStatus.SUCCESS)

        failed_packages = [node.package for node in failed_nodes]
        successful_packages = [node.package for node in successful_nodes]

        return NotificationData(
            failed_packages=failed_packages,
            successful_packages=successful_packages,
            dag_nodes=dag.nodes,
            pipeline_urls=pipeline_urls,
            package_comparison_urls={},
        )

    def send_workspace_notification(self, workspace_name: str, data: NotificationData) -> bool:
        """
        Send notification for a workspace, creating notification target if needed.

        Args:
            workspace_name: Name of the workspace
            data: Notification data containing build results

        Returns:
            True if notification was sent successfully, False otherwise
        """
        try:
            title = f"Scheduler Report for {workspace_name}"

            notification_id = self.find_notification_target_by_title(title)

            if not notification_id:
                description = f"Automated scheduler reports and state storage for workspace '{workspace_name}'"
                notification_id = self.create_notification_target(title, description)

            return self.send_notification(notification_id, data)
        except (OSError, ValueError):
            return False
