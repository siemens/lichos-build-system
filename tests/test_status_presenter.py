# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from lichoscli.commands.status import StatusCommand
from tests.mocks import create_mock_args


def test_status_style_maps_success_without_type_error(mock_di_container):
    command = StatusCommand(mock_di_container, create_mock_args(package=None))

    assert command._status_style("success") == "success"


def test_status_style_maps_failure(mock_di_container):
    command = StatusCommand(mock_di_container, create_mock_args(package=None))

    assert command._status_style("failed") == "error"
