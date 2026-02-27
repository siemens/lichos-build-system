# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import MagicMock, patch

import pytest

from lichoscli.commands.show import ShowCommand
from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    args = create_mock_args()
    args.package = "mypkg"
    args.branches = False
    args.mr = False
    args.mr_all = False
    args.dump = False
    return args


def test_show_package_not_found(mock_di_container, mock_args):
    """Test execution when package is not found."""
    package_service = mock_di_container.package_service
    package_service.get_package.return_value = None

    cmd = ShowCommand(mock_di_container, mock_args)
    ret = cmd.execute()

    assert ret == 1
    package_service.get_package.assert_called_once_with("mypkg")


def test_show_package_info_success(mock_di_container, mock_args):
    """Test successful execution showing package info."""
    package_service = mock_di_container.package_service
    pkg = MagicMock()
    pkg.id = "pkgid"
    pkg.name = "mypkg"
    pkg.path = "/some/path"
    pkg.builds_access_level = "private"
    pkg.default_branch = "main"
    pkg.attributes = {}
    pkg.variables.list.return_value = []
    package_service.get_package.return_value = pkg
    package_service.pretty_format_ci_path.return_value = "formatted_path"

    cmd = ShowCommand(mock_di_container, mock_args)
    ret = cmd.execute()

    assert ret == 0
    package_service.get_package.assert_called_once_with("mypkg")


def test_show_branches_success(mock_di_container, mock_args):
    """Test successful execution showing branches."""
    package_service = mock_di_container.package_service
    mock_args.branches = True
    pkg = MagicMock()
    pkg.name = "mypkg"
    branch = MagicMock()
    branch.commit = {"id": "abcdef123456", "committed_date": "2024-01-01T00:00:00Z"}
    branch.protected = True
    branch.name = "feature"
    pkg.branches.list.return_value = [branch]
    package_service.get_package.return_value = pkg

    with patch("lichoscli.commands.show.parser.isoparse") as mock_isoparse:
        from datetime import datetime, timedelta, timezone

        mock_isoparse.return_value = datetime.now(timezone.utc) - timedelta(days=5)

        cmd = ShowCommand(mock_di_container, mock_args)
        ret = cmd.execute()

        assert ret == 0
        package_service.get_package.assert_called_once_with("mypkg")


def test_show_branches_none(mock_di_container, mock_args):
    """Test execution when no branches found."""
    package_service = mock_di_container.package_service
    mock_args.branches = True
    pkg = MagicMock()
    pkg.name = "mypkg"
    pkg.branches.list.return_value = []
    package_service.get_package.return_value = pkg

    cmd = ShowCommand(mock_di_container, mock_args)
    ret = cmd.execute()

    assert ret == 1
    package_service.get_package.assert_called_once_with("mypkg")
