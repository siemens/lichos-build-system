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


def _project_with_ci_config(path):
    project = GitLabProject(Mock())
    project._project.ci_config_path = path
    return project


def test_oci_ci_config_marks_project_as_oci():
    """A project wired to oci.yml must be recognised as an oci project."""
    project = _project_with_ci_config("oci.yml@si-ds-fg/platform-os/pkg/00ci")

    assert project.is_oci is True
    assert project.is_image is False
    assert project.is_package is False


def test_gbp_ci_config_is_not_an_oci():
    """Package projects must not be mistaken for oci projects."""
    project = _project_with_ci_config("gbp.yml@si-ds-fg/platform-os/pkg/00ci")

    assert project.is_oci is False
    assert project.is_package is True
