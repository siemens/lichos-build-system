import pytest
from unittest.mock import MagicMock, patch
from lichoscli.commands.show import ShowCommand


@pytest.fixture
def mock_pkg():
    pkg = MagicMock()
    pkg.id = "pkgid"
    pkg.path = "/some/path"
    pkg.builds_access_level = "private"
    pkg.default_branch = "main"
    pkg.ci_config_path = "/some/.gitlab-ci.yml"
    pkg.attributes = {}
    pkg.branches.list.return_value = []
    return pkg


@pytest.fixture
def mock_pkg_with_fork(mock_pkg):
    mock_pkg.attributes = {
        "forked_from_project": {"path_with_namespace": "group/parent"}
    }
    return mock_pkg


@pytest.fixture
def mock_args():
    class Args:
        package = "mypkg"
        branches = False

    return Args()


def test_show_package_info(monkeypatch, mock_pkg, mock_args):
    handler = MagicMock()
    handler.get_package.return_value = mock_pkg
    mock_args.branches = False

    with patch(
        "lichoscli.commands.show.CIConfigUtils.get_type_from_ci_path",
        return_value="gitlab",
    ):
        cmd = ShowCommand(handler, mock_args)
        # Patch print to capture output
        with patch("builtins.print") as mock_print:
            ret = cmd.execute()
            assert ret == 0
            assert mock_print.called


def test_show_package_info_with_fork(monkeypatch, mock_pkg_with_fork, mock_args):
    handler = MagicMock()
    handler.get_package.return_value = mock_pkg_with_fork
    mock_args.branches = False

    with patch(
        "lichoscli.commands.show.CIConfigUtils.get_type_from_ci_path",
        return_value="gitlab",
    ):
        cmd = ShowCommand(handler, mock_args)
        with patch("builtins.print") as mock_print:
            ret = cmd.execute()
            assert ret == 0
            assert mock_print.called


def test_show_package_not_found(mock_args):
    handler = MagicMock()
    handler.get_package.return_value = None
    cmd = ShowCommand(handler, mock_args)
    with patch("builtins.print") as mock_print:
        ret = cmd.execute()
        assert ret == 1
        assert "not found" in mock_print.call_args[0][0]


def test_show_branches(monkeypatch, mock_args):
    handler = MagicMock()
    mock_args.branches = True
    pkg = MagicMock()
    branch = MagicMock()
    branch.commit = {"id": "abcdef123456", "committed_date": "2024-01-01T00:00:00Z"}
    branch.protected = True
    branch.name = "feature"
    pkg.branches.list.return_value = [branch]
    handler.get_package.return_value = pkg

    with patch("lichoscli.commands.show.parser.isoparse") as mock_isoparse:
        from datetime import datetime, timezone, timedelta

        mock_isoparse.return_value = datetime.now(timezone.utc) - timedelta(days=5)
        cmd = ShowCommand(handler, mock_args)
        with patch("builtins.print") as mock_print:
            ret = cmd.execute()
            assert ret == 0
            assert mock_print.called


def test_show_branches_none(monkeypatch, mock_args):
    handler = MagicMock()
    mock_args.branches = True
    pkg = MagicMock()
    pkg.branches.list.return_value = []
    handler.get_package.return_value = pkg

    cmd = ShowCommand(handler, mock_args)
    with patch("builtins.print") as mock_print:
        ret = cmd.execute()
        assert ret == 1
        assert "No branches found" in mock_print.call_args[0][0]
