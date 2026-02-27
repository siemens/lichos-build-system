# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from lichoscli.commands.list import ListCommand
from tests.mocks import MockGitLabProject, create_mock_args


def test_command_initialization_sets_correct_attributes(mock_di_container):
    """Test that command initialization sets correct attributes."""
    args = create_mock_args()
    command = ListCommand(mock_di_container, args)

    assert command.di_container == mock_di_container
    assert command.args == args


def test_list_command_mock_package():
    """Test mock package creation for list command."""
    mock_package1 = MockGitLabProject(
        name="package1",
        id=1,
        ci_config_path="gbp.yml@test-group/pkg/00ci",
        namespace={"full_path": "test-group/pkg", "path": "pkg"},
    )


def test_execute_gets_packages_and_returns_success(mock_di_container):
    """Test successful execution calls get_all_packages and returns 0."""
    args = create_mock_args()

    mock_package1 = MockGitLabProject(name="package1", id=1, ci_config_path="gbp.yml@test-group/pkg/00ci")
    mock_package2 = MockGitLabProject(
        name="package2",
        id=2,
        ci_config_path="gbp.yml@test-group/pkg/00ci",
        default_branch="develop",
        builds_access_level="disabled",
    )

    package_service = mock_di_container.package_service
    package_service.get_all_packages.return_value = [mock_package1, mock_package2]
    package_service.pretty_format_ci_path.return_value = "gbp"
    package_service.get_display_name.side_effect = lambda pkg: pkg.name

    # Mock the DI container's group_rpath attribute
    mock_di_container.group_rpath = "test-group/pkg"

    command = ListCommand(mock_di_container, args)
    result = command.execute()

    assert result == 0
    package_service.get_all_packages.assert_called_once()


def test_execute_with_empty_package_list(mock_di_container):
    """Test execution with empty package list returns 0."""
    args = create_mock_args()

    package_service = mock_di_container.package_service
    package_service.get_all_packages.return_value = []

    # Mock the DI container's group_rpath attribute
    mock_di_container.group_rpath = "test-group/pkg"

    command = ListCommand(mock_di_container, args)
    result = command.execute()

    assert result == 0
    package_service.get_all_packages.assert_called_once()


def test_execute_handles_package_with_subgroup_namespace(mock_di_container):
    """Test execution handles packages in subgroups correctly."""
    args = create_mock_args()

    mock_package = MockGitLabProject(
        name="package4",
        id=4,
        ci_config_path="gbp.yml@test-group/pkg/00ci",
        namespace={"full_path": "test-group/pkg/subgroup", "path": "subgroup"},
    )

    package_service = mock_di_container.package_service
    package_service.get_all_packages.return_value = [mock_package]
    package_service.pretty_format_ci_path.return_value = "gbp"
    package_service.get_display_name.side_effect = lambda pkg: "subgroup/package4"

    # Mock the DI container's group_rpath attribute
    mock_di_container.group_rpath = "test-group/pkg"

    command = ListCommand(mock_di_container, args)
    result = command.execute()

    assert result == 0
    package_service.get_all_packages.assert_called_once()
