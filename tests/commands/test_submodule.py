# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from pathlib import Path

import pytest

from lichoscli.commands.submodule import SubmoduleCommand
from lichoscli.core.exceptions import BranchError, ServiceError
from lichoscli.core.models.git import GitSubmodule, SubmoduleChange
from lichoscli.core.services import SubmoduleService
from tests.mocks import create_mock_args

CHANGE = SubmoduleChange(None, GitSubmodule("package-a", "package-a", "a" * 40, "git@gitlab.example.com:group/a.git"))


@pytest.fixture
def submodule_service(mock_di_container):
    mock_di_container.group_rpath = "group"
    return mock_di_container.obtain_ref(SubmoduleService)


def run(mock_di_container, push=False, **kwargs):
    return SubmoduleCommand(mock_di_container, create_mock_args(push=push, **kwargs)).execute()


def test_create_passes_the_project_location_and_remote(mock_di_container, submodule_service, tmp_path):
    submodule_service.create.return_value = [CHANGE]

    assert run(mock_di_container, subcommand="create", project_name="snapshot", output_dir=str(tmp_path)) == 0

    submodule_service.create.assert_called_once_with(
        tmp_path / "snapshot", "main", "git@gitlab.example.com:group/snapshot.git", False
    )


def test_update_passes_the_resolved_path_and_push_flag(mock_di_container, submodule_service, tmp_path):
    submodule_service.update.return_value = []

    assert run(mock_di_container, subcommand="update", path=str(tmp_path), push=True) == 0

    submodule_service.update.assert_called_once_with(Path(tmp_path).resolve(), "main", True)


@pytest.mark.parametrize("error", [BranchError("no members"), ServiceError("push failed")])
def test_update_reports_service_failures_as_an_error(mock_di_container, submodule_service, tmp_path, error):
    submodule_service.update.side_effect = error

    assert run(mock_di_container, subcommand="update", path=str(tmp_path)) == 1


def test_unknown_subcommand_is_an_error(mock_di_container, submodule_service):
    assert run(mock_di_container, subcommand=None) == 1
