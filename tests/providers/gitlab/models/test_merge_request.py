# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from gitlab import GitlabGetError

from lichoscli.providers.gitlab.models.merge_request import GitLabMergeRequest


def test_is_approved_when_no_required_approvals_are_left():
    gitlab_mr = Mock()
    gitlab_mr.approvals.get.return_value = Mock(approvals_left=0)

    assert GitLabMergeRequest(gitlab_mr).is_approved() is True


def test_is_not_approved_when_required_approvals_are_left():
    gitlab_mr = Mock()
    gitlab_mr.approvals.get.return_value = Mock(approvals_left=1)

    assert GitLabMergeRequest(gitlab_mr).is_approved() is False


def test_is_approved_supports_direct_approved_flag():
    gitlab_mr = Mock()
    approval = Mock(spec=["approved"])
    approval.approved = True
    gitlab_mr.approvals.get.return_value = approval

    assert GitLabMergeRequest(gitlab_mr).is_approved() is True


def test_is_approved_fails_closed_when_gitlab_check_fails():
    gitlab_mr = Mock()
    gitlab_mr.iid = 42
    gitlab_mr.approvals.get.side_effect = GitlabGetError("unavailable")

    assert GitLabMergeRequest(gitlab_mr).is_approved() is False
