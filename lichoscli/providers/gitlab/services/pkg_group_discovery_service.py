# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab implementation of PkgGroupDiscoveryService."""

import logging
from typing import Any, Callable, List, Optional

from lichoscli.core.services.pkg_group_discovery import PkgGroupDiscoveryService
from lichoscli.providers.gitlab.client import GitLabClientFactory

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
