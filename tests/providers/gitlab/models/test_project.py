# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

from gitlab.exceptions import GitlabCreateError

from lichoscli.providers.gitlab.models.project import GitLabProject


def _make_project():
    return GitLabProject(Mock())


@patch("lichoscli.providers.gitlab.models.project.GitUrl.sanitize_branch_name")
def test_protect_branch_success(mock_sanitize):
    mock_sanitize.return_value = "formatted-branch"
    project = _make_project()

    result = project.protect_branch("main")

    assert result is True
    project.protectedbranches.create.assert_called_once_with({"name": "formatted-branch"})


@patch("lichoscli.providers.gitlab.models.project.GitUrl.sanitize_branch_name")
def test_protect_branch_failure(mock_sanitize):
    mock_sanitize.return_value = "formatted-branch"
    project = _make_project()
    project.protectedbranches.create.side_effect = GitlabCreateError("Failed")

    result = project.protect_branch("main")

    assert result is False
