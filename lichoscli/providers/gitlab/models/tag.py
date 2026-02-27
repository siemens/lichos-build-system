# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Tag model wrapper."""

from datetime import datetime
from typing import Any, Optional

from gitlab.v4.objects import ProjectTag as GitLabTag

from lichoscli.core.models import Tag


class GitLabTag(Tag):
    """Wrapper for GitLab Tag objects."""

    def __init__(self, gitlab_tag: GitLabTag):
        self._tag = gitlab_tag

    @property
    def name(self) -> str:
        return self._tag.name

    @property
    def target(self) -> str:
        return self._tag.target

    @property
    def message(self) -> Optional[str]:
        return getattr(self._tag, "message", None)

    @property
    def protected(self) -> bool:
        return getattr(self._tag, "protected", False)

    @property
    def created_at(self) -> Optional[datetime]:
        created_at_str = getattr(self._tag, "created_at", None)
        if created_at_str:
            try:
                return datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None
        return None

    @property
    def commit(self) -> dict[str, Any]:
        return getattr(self._tag, "commit", {})

    @property
    def release(self) -> Optional[dict[str, Any]]:
        return getattr(self._tag, "release", None)

    def delete(self):
        """Delete the tag."""
        return self._tag.delete()
