# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""GitLab Tags collection wrapper."""

from typing import Optional

from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProject

from lichoscli.core.models import Tag, Tags

from .tag import GitLabTag


class GitLabTags(Tags):
    """Wrapper for GitLab Project Tags collection."""

    def __init__(self, gitlab_project: GitLabProject):
        self._project = gitlab_project

    def list(self) -> list[Tag]:
        """Get all tags in this collection."""
        return [GitLabTag(tag) for tag in self._project.tags.list(all=True)]

    def get(self, name: str) -> Optional[Tag]:
        """Get a specific tag by name."""
        try:
            tag = self._project.tags.get(name)
            return GitLabTag(tag)
        except GitlabError:
            return None

    def create(self, name: str, target: str, message: Optional[str] = None) -> Tag:
        """Create a new tag."""
        tag_data = {"tag_name": name, "ref": target}
        if message:
            tag_data["message"] = message
        tag = self._project.tags.create(tag_data)
        return GitLabTag(tag)

    def delete(self, name: str) -> bool:
        """Delete a tag by name."""
        try:
            tag = self._project.tags.get(name)
            tag.delete()
            return True
        except GitlabError:
            return False

    def exists(self, name: str) -> bool:
        """Check if a tag exists by name."""
        try:
            self._project.tags.get(name)
            return True
        except GitlabError:
            return False
