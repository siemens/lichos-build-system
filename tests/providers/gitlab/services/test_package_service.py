# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from lichoscli.providers.gitlab.services.package_service import GitLabPackageService


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
