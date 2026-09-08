# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

import pytest

from lichoscli.commands.fork import ForkCommand


@pytest.fixture
def mock_fork_args(mock_args):
    args = mock_args()
    args.package = "test-package"
    args.namespace = "target-group/pkg"
    return args


@pytest.fixture
def mock_ci_project(mock_gitlab_project):
    project = mock_gitlab_project()
    project.name = "00ci"
    project.forked_from_project = {"namespace": {"full_path": "source-group/pkg"}}
    return project


@patch("lichoscli.commands.fork.CIConfigUtils")
def test_fork_command_initialization(mock_ci_config_utils, mock_di_container, mock_fork_args):
    mock_di_container.group_rpath = "test-group/pkg"
    mock_ci_config_utils.is_forked.return_value = True
    mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"

    mock_ci_package = Mock()
    mock_ci_package.is_fork = False
    mock_di_container.package_service.get_package.return_value = None
    command = ForkCommand(mock_di_container, mock_fork_args)

    assert command.args.package == "test-package"
    assert command.destination_namespace == "target-group/pkg"


@patch("lichoscli.commands.fork.CIConfigUtils")
def test_detect_fork_configuration_auto_detect(mock_ci_config_utils, mock_di_container, mock_ci_project):
    mock_di_container.group_rpath = "current-group/pkg"
    mock_args_auto = Mock()
    mock_args_auto.package = "test-package"
    mock_args_auto.namespace = None

    mock_ci_project.is_fork = True
    mock_ci_project.parent_project_namespace = "source-group/pkg"
    mock_di_container.package_service.get_package.return_value = mock_ci_project

    command = ForkCommand(mock_di_container, mock_args_auto)

    assert command.source_namespace == "source-group/pkg"
    assert command.destination_namespace == "current-group/pkg"


@patch("lichoscli.commands.fork.CIConfigUtils")
@patch("lichoscli.commands.fork.HierarchyUtils")
def test_execute_successful_fork(
    mock_hierarchy_utils,
    mock_ci_config_utils,
    mock_di_container,
    mock_fork_args,
    mock_gitlab_project,
):
    mock_di_container.group_rpath = "target-group/pkg"
    mock_ci_config_utils.is_forked.return_value = True
    mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
    mock_ci_config_utils.get_ci_path.return_value = "target-group/pkg/00ci/.gitlab-ci.yml"

    mock_destination_ci = mock_gitlab_project()
    mock_destination_ci.name = "00ci"

    mock_forked_package = mock_gitlab_project()
    mock_forked_package.name = "test-package"

    mock_di_container.package_service.hierarchy_exists.return_value = True

    mock_base_package = mock_gitlab_project()
    mock_base_package.name = "test-package"
    mock_base_package.path_with_namespace = "source-group/pkg/test-package"

    def lookup(name, include_archived=False, namespace=None):
        if namespace is None:
            return None  # no 00ci in the current group
        return {"00ci": mock_destination_ci, "test-package": mock_base_package}.get(name)

    mock_di_container.package_service.get_package.side_effect = lookup

    mock_hierarchy_utils.extract_package_subpath.return_value = ""

    command = ForkCommand(mock_di_container, mock_fork_args)
    command.destination_namespace = "target-group/pkg"

    result = command.execute()

    assert result == 0


@patch("lichoscli.commands.fork.CIConfigUtils")
def test_execute_hierarchy_not_exists(mock_ci_config_utils, mock_di_container, mock_fork_args):
    mock_di_container.group_rpath = "target-group/pkg"
    mock_ci_config_utils.is_forked.return_value = True
    mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"

    # Mock the projects object that gets returned by get_projects()
    mock_projects = Mock()
    mock_projects.hierarchy_exists.return_value = False
    mock_di_container.package_service.get_projects.return_value = mock_projects
    mock_di_container.package_service.get_package.return_value = None  # No 00ci package

    command = ForkCommand(mock_di_container, mock_fork_args)
    result = command.execute()

    assert result == 1


@patch("lichoscli.commands.fork.CIConfigUtils")
def test_execute_dry_run(mock_ci_config_utils, mock_di_container, mock_fork_args):
    mock_di_container.group_rpath = "target-group/pkg"
    mock_ci_config_utils.is_forked.return_value = True
    mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"

    mock_fork_args.dry = True
    mock_di_container.package_service.get_package.return_value = None  # No 00ci package
    command = ForkCommand(mock_di_container, mock_fork_args)

    with patch.object(command, "_dry_run_preview", return_value=0) as mock_dry_run:
        result = command.execute()

    assert result == 0
    mock_dry_run.assert_called_once()
