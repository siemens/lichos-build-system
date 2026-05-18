# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of PkgGroupDiscoveryService."""

import logging
from typing import Any, Callable, List, Optional

from gitlab import GitlabError

from lichoscli.core.services.pkg_group_discovery import PkgGroupDiscoveryService

logger = logging.getLogger(__name__)


class GitLabPkgGroupDiscoveryService(PkgGroupDiscoveryService):
    """Search GitLab projects by name and return the namespace group paths."""

    def __init__(self, gitlab_client: Any, client_factory: Callable[[str], Any]) -> None:
        self._default_client = gitlab_client
        self._client_factory = client_factory

    def search_pkg_groups(self, query: str, host: Optional[str] = None) -> List[str]:
        """Return sorted, deduplicated group paths whose projects exactly match *query*."""
        
        if host:
            logger.debug("Creating GitLab client for host %s to search pkg groups", host)
            gl = self._client_factory(host)
        else:
            gl = self._default_client

        logger.debug("Searching GitLab for projects matching '%s'", query)
        try:
            projects = gl.projects.list(search=query, get_all=True)
        except (AttributeError, TypeError) as exc:
            logger.debug("GitLab project search failed: %s", exc)
            return []

        seen = set()
        results = []
        for project in projects:
            if project.name != query:
                continue
            namespace = project.namespace.get("full_path", "") if hasattr(project, "namespace") else ""
            if namespace and namespace not in seen:
                seen.add(namespace)
                results.append(namespace)

        results.sort()
        logger.debug("Found %d pkg group(s) matching '%s'", len(results), query)
        return results

    def get_group_id(self, group_path: str) -> Optional[int]:
        """Return the numeric ID of a GitLab group, or None if not found."""
        try:
            group = self._default_client.groups.get(group_path)
            return group.id
        except (GitlabError, AttributeError) as exc:
            logger.debug("Group '%s' not found: %s", group_path, exc)
            return None

    def create_group(
        self,
        name: str,
        path: str,
        parent_id: Optional[int] = None,
        description: str = "",
        visibility: str = "internal",
    ) -> int:
        """Create a GitLab group and return its numeric ID."""
        group_data = {
            "name": name,
            "path": path,
            "description": description,
            "visibility": visibility,
        }
        if parent_id is not None:
            group_data["parent_id"] = parent_id
        group = self._default_client.groups.create(group_data)
        return group.id
