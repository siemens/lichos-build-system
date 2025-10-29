"""GitLab MergeRequest model wrapper."""

import logging
from typing import Any

from gitlab import GitlabError
from gitlab.v4.objects import MergeRequest as GitLabMergeRequestModel

from lichoscli.core.models import MergeRequest

logger = logging.getLogger(__name__)


class GitLabMergeRequest(MergeRequest):
    """Wrapper for GitLab MergeRequest objects."""

    def __init__(self, gitlab_mr: GitLabMergeRequestModel):
        self._mr = gitlab_mr

    @property
    def id(self) -> str:
        return str(self._mr.id)

    @property
    def iid(self) -> str:
        return str(self._mr.iid)

    @property
    def title(self) -> str:
        return self._mr.title

    @property
    def author(self) -> dict[str, Any]:
        return getattr(self._mr, "author", {})

    @property
    def created_at(self) -> str:
        return getattr(self._mr, "created_at", "")

    @property
    def source_branch(self) -> str:
        return self._mr.source_branch

    @property
    def target_branch(self) -> str:
        return self._mr.target_branch

    @property
    def web_url(self) -> str:
        return self._mr.web_url

    @property
    def state(self) -> str:
        return self._mr.state

    def create_pipeline(self) -> int:
        """Create/trigger a pipeline for this merge request.

        Returns:
            Pipeline ID on success, raises exception on failure.
        """
        pipeline = self._mr.pipelines.create()
        return pipeline.id

    def merge(self) -> bool:
        """Merge this merge request.

        Returns:
            True if merge was successful, False otherwise.
        """
        try:
            self._mr.merge()
            return True
        except GitlabError as e:
            logger.error("Failed to merge MR !%s: %s", self.iid, str(e))
            return False
