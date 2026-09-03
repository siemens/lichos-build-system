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


def test_delete_success():
    project = _make_project()

    result = project.delete()

    assert result is True
    project._project.delete.assert_called_once_with()


def test_delete_failure():
    from gitlab.exceptions import GitlabDeleteError

    project = _make_project()
    project._project.delete.side_effect = GitlabDeleteError("Failed")

    result = project.delete()

    assert result is False


def test_delete_permanently_success():
    """delete_permanently() re-fetches the project (GitLab renames it the
    moment it's marked for deletion, so any path captured before that first
    delete() is stale) and deletes using its current full_path."""
    project = _make_project()
    project._project.id = 42

    refetched = Mock()
    refetched.path_with_namespace = "test-group/pkg-deleted-42"
    project._project.manager.gitlab.projects.get.return_value = refetched

    result = project.delete_permanently()

    assert result is True
    project._project.manager.gitlab.projects.get.assert_called_once_with(42)
    refetched.delete.assert_called_once_with(permanently_remove=True, full_path="test-group/pkg-deleted-42")


def test_delete_permanently_failure():
    from gitlab.exceptions import GitlabDeleteError

    project = _make_project()
    project._project.manager.gitlab.projects.get.side_effect = GitlabDeleteError("Failed")

    result = project.delete_permanently()

    assert result is False


def test_is_marked_for_deletion_true():
    project = _make_project()
    project._project.marked_for_deletion_at = "2024-01-01T00:00:00Z"

    assert project.is_marked_for_deletion is True


def test_is_marked_for_deletion_false():
    project = _make_project()
    project._project.marked_for_deletion_at = None
    project._project.marked_for_deletion_on = None

    assert project.is_marked_for_deletion is False


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
