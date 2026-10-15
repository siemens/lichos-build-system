# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import pytest

from lichoscli.providers.gitlab.models import GitLabProjects
from lichoscli.providers.gitlab.services.package_service import GitLabPackageService


def test_get_projects_returns_concrete_collection(mock_gitlab):
    service = GitLabPackageService("test-group/pkg", mock_gitlab())

    projects = service.get_projects()

    assert isinstance(projects, GitLabProjects)
    assert projects.path == "test-group/pkg"


@pytest.mark.parametrize("name", ["package1", "package4", "missing"])
def test_projects_get_finds_projects_including_subgroups(mock_gitlab, name):
    service = GitLabPackageService("test-group/pkg", mock_gitlab())

    project = service.get_projects().get(name)

    if name == "missing":
        assert project is None
    else:
        assert project.name == name


def test_projects_get_excludes_archived_projects(mock_gitlab):
    gitlab = mock_gitlab()
    gitlab.projects.get(1).archived = True
    service = GitLabPackageService("test-group/pkg", gitlab)

    assert service.get_projects().get("package1") is None


def test_get_package_excludes_archived_projects_by_default(mock_gitlab):
    gitlab = mock_gitlab()
    archived_project = gitlab.projects.get(1)
    archived_project.archived = True

    service = GitLabPackageService("test-group/pkg", gitlab)

    assert service.get_package("package1") is None


def test_get_package_can_include_archived_projects(mock_gitlab):
    gitlab = mock_gitlab()
    archived_project = gitlab.projects.get(1)
    archived_project.archived = True

    service = GitLabPackageService("test-group/pkg", gitlab)

    package = service.get_package("package1", include_archived=True)

    assert package is not None
    assert package.archived is True


def test_get_all_packages_can_include_archived_projects(mock_gitlab):
    gitlab = mock_gitlab()
    archived_project = gitlab.projects.get(1)
    archived_project.archived = True

    service = GitLabPackageService("test-group/pkg", gitlab)

    active_packages = service.get_all_packages()
    all_packages = service.get_all_packages(include_archived=True)

    assert {package.name for package in active_packages} == {
        "package2",
        "package3",
        "package4",
    }
    assert {package.name for package in all_packages} == {
        "package1",
        "package2",
        "package3",
        "package4",
    }
