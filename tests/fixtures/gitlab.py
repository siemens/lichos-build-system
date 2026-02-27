# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""
GitLab-specific fixtures and mocks.
"""

from unittest.mock import Mock

import pytest

from tests.mocks import MockGitLab, MockGitLabGroup, MockGitLabProject


@pytest.fixture
def mock_gitlab_project():
    """Create a mock GitLab project with commonly needed attributes."""

    def _create_project(**kwargs):
        project = MockGitLabProject()
        project.id = kwargs.get("id", 123)
        project.name = kwargs.get("name", "test-package")
        project.ci_config_path = kwargs.get("ci_config_path", ".gitlab-ci.yml")
        project.builds_access_level = kwargs.get("builds_access_level", "enabled")
        project.default_branch = kwargs.get("default_branch", "main")
        project.namespace = kwargs.get("namespace", {"id": 456, "full_path": "test-group/pkg"})
        return project

    return _create_project


@pytest.fixture
def mock_package(mock_gitlab_project):
    """Create a mock package with commonly needed attributes for commands."""
    pkg = mock_gitlab_project()
    pkg.web_url = "https://gitlab.example.com/test-group/test-package"

    # Mock variables
    variables = Mock()
    variable = Mock()
    variable.key = "CUSTOM_VAR"
    variable.value = "value"
    variables.list.return_value = [variable]
    pkg.variables = variables

    pipelines = Mock()
    pipeline = Mock()

    jobs = Mock()
    job = Mock()
    job.name = "calculate-env"

    artifacts = Mock()
    artifacts.download_as_directory.return_value = Mock(name="/tmp/test")
    job.artifacts = artifacts

    jobs.get_by_name.return_value = job
    pipeline.jobs = jobs
    pipelines.get_latest.return_value = pipeline
    pkg.pipelines = pipelines

    return pkg


@pytest.fixture
def mock_gitlab():
    """Create a comprehensive mock GitLab instance."""

    def _create_gitlab(**kwargs):
        mock_gitlab = MockGitLab()
        mock_projects = [
            MockGitLabProject(name="package1", id=1),
            MockGitLabProject(name="package2", id=2, builds_access_level="disabled"),
            MockGitLabProject(name="package3", id=3, default_branch="develop"),
        ]
        group_rpath = "test-group/pkg"
        subproject = MockGitLabProject(
            name="package4",
            id=4,
            namespace={"full_path": "test-group/pkg/subgroup", "path": "subgroup"},
        )
        mock_subgroup = MockGitLabGroup(projects=[subproject], id=789)
        mock_group = MockGitLabGroup(projects=mock_projects, subgroups=[mock_subgroup])

        mock_gitlab.add_group(group_rpath, mock_group)
        mock_gitlab.add_group("test-group/pkg/subgroup", mock_subgroup)

        mock_gitlab.groups.get.side_effect = lambda group_rpath_or_id: {
            "test-group/pkg": mock_group,
            "test-group/pkg/subgroup": mock_subgroup,
            456: mock_group,
            789: mock_subgroup,
        }.get(group_rpath_or_id, None)

        for project in mock_projects + [subproject]:
            mock_gitlab.add_project(project.id, project)

        return mock_gitlab

    return _create_gitlab


@pytest.fixture
def mock_pipeline():
    """Create a mock GitLab pipeline."""

    def _create_pipeline(**kwargs):
        pipeline = Mock()
        pipeline.id = kwargs.get("id", 789)
        pipeline.status = kwargs.get("status", "success")
        pipeline.ref = kwargs.get("ref", "main")
        pipeline.created_at = kwargs.get("created_at", "2023-01-01T00:00:00Z")
        return pipeline

    return _create_pipeline


@pytest.fixture
def mock_job():
    """Create a mock GitLab job."""

    def _create_job(**kwargs):
        job = Mock()
        job.id = kwargs.get("id", 123)
        job.status = kwargs.get("status", "pending")
        job.name = kwargs.get("name", "test-job")
        job.ref = kwargs.get("ref", "main")
        job.created_at = kwargs.get("created_at", "2023-01-01T00:00:00Z")
        job.project_id = kwargs.get("project_id", 456)
        return job

    return _create_job


@pytest.fixture
def mock_author():
    """Create a mock author."""

    def _create_author(name="Test Author", email="test@example.com"):
        author = Mock()
        author.name = name
        author.email = email
        return author

    return _create_author
