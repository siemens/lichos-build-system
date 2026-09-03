# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

import pytest
from gitlab import GitlabGetError

from lichoscli.core.exceptions import MergeRequestError
from lichoscli.providers.gitlab.models.merge_requests import GitLabMergeRequests


def test_list_can_raise_when_merge_requests_cannot_be_verified():
    gitlab_project = Mock()
    gitlab_project.mergerequests.list.side_effect = GitlabGetError("unavailable")

    with pytest.raises(MergeRequestError):
        GitLabMergeRequests(gitlab_project).list(raise_on_error=True)


def test_list_preserves_empty_fallback_by_default():
    gitlab_project = Mock()
    gitlab_project.mergerequests.list.side_effect = GitlabGetError("unavailable")

    assert GitLabMergeRequests(gitlab_project).list() == []
