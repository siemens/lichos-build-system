# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import patch

import pytest

from lichoscli.commands.hierarchy import HierarchyCommand


@pytest.fixture
def mock_hierarchy_args(mock_args):
    args = mock_args()
    args.target_path = "target-group/pkg"
    return args


@pytest.fixture
def hierarchy_command(mock_di_container, mock_hierarchy_args):
    mock_di_container.group_rpath = "test-group/pkg"
    return HierarchyCommand(mock_di_container, mock_hierarchy_args)


def test_hierarchy_command_initialization(hierarchy_command, mock_hierarchy_args):
    """Test that hierarchy command initialization sets correct attributes."""
    assert hierarchy_command.args.target_path == "target-group/pkg"


def test_execute_dry_run(hierarchy_command, mock_hierarchy_args):
    """Test execution in dry run mode."""
    mock_hierarchy_args.dry = True

    with patch.object(hierarchy_command, "_dry_run_preview", return_value=0) as mock_dry_run:
        result = hierarchy_command.execute()

    assert result == 0
    mock_dry_run.assert_called_once()
