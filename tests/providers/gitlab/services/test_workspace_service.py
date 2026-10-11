# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

import pytest
from gitlab import GitlabGetError

from lichoscli.core.exceptions import ProviderAPIError
from lichoscli.providers.gitlab.services.workspace_service import GitLabWorkspaceService


def project(name, is_package=True, is_image=False):
    item = Mock()
    item.name = name
    item.is_package = is_package
    item.is_image = is_image
    item.branches.get.return_value.commit = {"id": "a" * 40}
    return item


def service(*projects):
    package_service = Mock()
    package_service.get_all_packages.return_value = list(projects)
    return GitLabWorkspaceService(package_service)


def test_workspace_heads_contain_packages_and_images_sorted_by_name():
    package, image, tool = project("package-a"), project("image-qemu", False, True), project("tool", False)

    heads = service(package, image, tool).get_workspace_heads("flocken")

    assert heads == [(image, "a" * 40), (package, "a" * 40)]


def test_workspace_heads_skip_projects_without_the_branch():
    missing = project("package-b")
    missing.branches.get.side_effect = GitlabGetError("404 Branch Not Found", response_code=404)

    assert [p.name for p, _ in service(project("package-a"), missing).get_workspace_heads("flocken")] == ["package-a"]


def test_workspace_heads_fail_when_a_branch_lookup_fails():
    broken = project("package-a")
    broken.branches.get.side_effect = GitlabGetError("502 Bad Gateway", response_code=502)

    with pytest.raises(ProviderAPIError):
        service(broken).get_workspace_heads("flocken")
