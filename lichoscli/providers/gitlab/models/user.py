# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab User model wrapper."""

from typing import Optional

from lichoscli.core.models import User


class GitLabUser(User):
    """Wrapper for GitLab User objects."""

    def __init__(self, gitlab_user):
        """Initialize with a GitLab user object.

        Args:
            gitlab_user: A GitLab user object, could be from pipeline.user or other GitLab API objects
        """
        self._user = gitlab_user

    @property
    def id(self) -> int:
        """User ID."""
        return getattr(self._user, "id", 0)

    @property
    def username(self) -> str:
        """Username."""
        return getattr(self._user, "username", "unknown")

    @property
    def name(self) -> Optional[str]:
        """Full name of the user."""
        return getattr(self._user, "name", None)

    @property
    def email(self) -> Optional[str]:
        """Email address of the user."""
        return getattr(self._user, "email", None)

    @property
    def web_url(self) -> Optional[str]:
        """Web URL to user profile."""
        return getattr(self._user, "web_url", None)

    @property
    def gitlab_user(self):
        """Access to underlying GitLab user object for provider-specific operations."""
        return self._user
