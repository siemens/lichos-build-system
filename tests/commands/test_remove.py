# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import pytest

from lichoscli.commands.remove import RemoveCommand
from tests.mocks import MockGitLabProject, create_mock_args


@pytest.fixture
def mock_args():
    args = create_mock_args()
    args.package = "test-package"
    return args


def _make_package(name="test-package"):
    return MockGitLabProject(name=name, path_with_namespace=f"test-group/pkg/{name}")


def test_package_not_found_returns_error(mock_di_container, mock_args):
    mock_di_container.package_service.get_package.return_value = None

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 1


def test_typed_name_mismatch_aborts_without_deleting(mock_di_container, mock_args):
    package = _make_package()
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "wrong-name"

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 1
    package.delete.assert_not_called()


def test_correct_name_deletes_but_declines_permanent(mock_di_container, mock_args):
    package = _make_package()
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "test-package"
    mock_di_container.user_interface.prompts.confirm.return_value = False

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    package.delete.assert_called_once()
    package.delete_permanently.assert_not_called()


def test_full_flow_permanently_deletes(mock_di_container, mock_args):
    package = _make_package()
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "test-package"
    mock_di_container.user_interface.prompts.confirm.return_value = True

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    package.delete.assert_called_once()
    package.delete_permanently.assert_called_once()


def test_permanent_confirm_but_second_typed_name_mismatch(mock_di_container, mock_args):
    package = _make_package()
    mock_di_container.package_service.get_package.return_value = package
    # First confirmation types correctly, second (permanent) types wrong.
    mock_di_container.user_interface.prompts.text_input.side_effect = ["test-package", "typo"]
    mock_di_container.user_interface.prompts.confirm.return_value = True

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    package.delete.assert_called_once()
    package.delete_permanently.assert_not_called()


def test_delete_failure_returns_error(mock_di_container, mock_args):
    package = _make_package()
    package.delete.return_value = False
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "test-package"

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 1


def test_permanent_delete_failure_returns_error(mock_di_container, mock_args):
    package = _make_package()
    package.delete_permanently.return_value = False
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "test-package"
    mock_di_container.user_interface.prompts.confirm.return_value = True

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 1


def test_already_marked_for_deletion_skips_straight_to_permanent(mock_di_container, mock_args):
    """A package already marked for deletion (e.g. a retried 'remove' after
    the first stage already ran) must skip the plain delete() -- GitLab
    rejects a second bare delete on an already-marked project -- and go
    straight to the permanent-delete confirmation."""
    package = _make_package(name="test-package-deletion_scheduled-1")
    package.is_marked_for_deletion = True
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "test-package-deletion_scheduled-1"

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    package.delete.assert_not_called()
    package.delete_permanently.assert_called_once()


def test_already_marked_for_deletion_aborts_on_name_mismatch(mock_di_container, mock_args):
    package = _make_package(name="test-package-deletion_scheduled-1")
    package.is_marked_for_deletion = True
    mock_di_container.package_service.get_package.return_value = package
    mock_di_container.user_interface.prompts.text_input.return_value = "wrong-name"

    command = RemoveCommand(mock_di_container, mock_args)
    result = command.execute()

    assert result == 0
    package.delete.assert_not_called()
    package.delete_permanently.assert_not_called()
