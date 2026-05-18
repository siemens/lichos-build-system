# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lichoscli.commands.collection import CollectionCommand


@pytest.fixture
def mock_collection_args(mock_args):
    args = mock_args()
    args.action = "create"
    args.target = "target-group/pkg"
    args.branch = "main"
    args.branch_explicitly_provided = True
    args.clone_all = False
    args.directory = None
    return args


@pytest.fixture
def collection_command(mock_di_container, mock_collection_args):
    mock_di_container.group_rpath = "test-group/pkg"
    mock_di_container.host = "gitlab.example.com"
    return CollectionCommand(mock_di_container, mock_collection_args)


# ------------------------------------------------------------------
# execute() dispatcher
# ------------------------------------------------------------------

def test_collection_command_initialization(collection_command, mock_collection_args):
    """Test that hierarchy command initialization sets correct attributes."""
    assert collection_command.args.target == "target-group/pkg"


def test_execute_no_action_returns_error(mock_di_container, mock_collection_args):
    """Test that execute() without an action returns non-zero."""
    mock_collection_args.action = None
    cmd = CollectionCommand(mock_di_container, mock_collection_args)
    assert cmd.execute() == 1


def test_execute_unknown_action_returns_error(collection_command, mock_collection_args):
    """Test that execute() with an unknown action returns non-zero."""
    mock_collection_args.action = "nonexistent"
    assert collection_command.execute() == 1


def test_validate_args_clone_requires_branch(mock_di_container, mock_collection_args):
    """Test that validate_args raises when --branch is missing for clone with a target."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.branch_explicitly_provided = False
    cmd = CollectionCommand(mock_di_container, mock_collection_args)
    with pytest.raises(ValueError, match="--branch is required"):
        cmd.validate_args()


def test_validate_args_clone_no_target_no_branch_required(mock_di_container, mock_collection_args):
    """Test that validate_args does not raise when no target is given (listing mode)."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = None
    mock_collection_args.branch_explicitly_provided = False
    cmd = CollectionCommand(mock_di_container, mock_collection_args)
    cmd.validate_args()  # should not raise


# ------------------------------------------------------------------
# action_create
# ------------------------------------------------------------------

def test_execute_create_dry_run(collection_command, mock_collection_args):
    """Test that hierarchy create --dry delegates to dry run preview."""
    mock_collection_args.action = "create"
    mock_collection_args.dry = True

    with patch.object(collection_command, "_create_dry_run_preview", return_value=0) as mock_dry_run:
        result = collection_command.execute()

    assert result == 0
    mock_dry_run.assert_called_once()


def test_execute_create_forks_core_packages(collection_command, mock_collection_args, mock_di_container):
    """Test that action_create forks required packages when hierarchy does not exist."""
    mock_collection_args.action = "create"
    mock_collection_args.dry = False
    mock_di_container.pkg_group_discovery.exists.return_value = False

    with patch.object(collection_command, "_create_target_hierarchy", return_value=True), \
         patch.object(collection_command, "_fork_required_packages", return_value=True):
        result = collection_command.action_create()

    assert result == 0


def test_execute_create_fork_failure_returns_error(collection_command, mock_collection_args, mock_di_container):
    """Test that action_create returns 1 when forking fails."""
    mock_collection_args.action = "create"
    mock_collection_args.dry = False
    mock_di_container.pkg_group_discovery.exists.return_value = False

    with patch.object(collection_command, "_create_target_hierarchy", return_value=True), \
         patch.object(collection_command, "_fork_required_packages", return_value=False):
        result = collection_command.action_create()

    assert result == 1


# ------------------------------------------------------------------
# action_clone — URL flow
# ------------------------------------------------------------------

def _make_package(name, ssh_url="git@gitlab.example.com/pkg.git", default_branch="main"):
    pkg = MagicMock()
    pkg.name = name
    pkg.ssh_url_to_repo = ssh_url
    pkg.default_branch = default_branch
    return pkg


def test_action_clone_url_writes_anchor(collection_command, mock_collection_args, tmp_path, monkeypatch):
    """Test that clone with a URL creates a directory and writes the anchor file."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = False
    monkeypatch.chdir(tmp_path)

    result = collection_command.action_clone()

    assert result == 0
    assert (tmp_path / "my-group").is_dir()
    collection_command.lichos_anchor_handler.write.assert_called_once_with(
        host="gitlab.example.com",
        pkg_group="my-org/my-group",
        branch="main",
        target_dir=Path("my-group"),
    )

def test_action_clone_url_custom_directory(collection_command, mock_collection_args, tmp_path, monkeypatch):
    """Test that clone with URL and explicit directory name uses that name."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.directory = "my-local-dir"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = False
    monkeypatch.chdir(tmp_path)

    result = collection_command.action_clone()

    assert result == 0
    assert (tmp_path / "my-local-dir").is_dir()
    collection_command.lichos_anchor_handler.write.assert_called_once_with(
        host="gitlab.example.com",
        pkg_group="my-org/my-group",
        branch="main",
        target_dir=Path("my-local-dir"),
    )

def test_action_clone_bare_path_with_host_writes_anchor(collection_command, mock_collection_args, tmp_path, monkeypatch):
    """Test that clone with a bare group path and a configured host succeeds."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "group/pkg"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = False
    monkeypatch.chdir(tmp_path)

    result = collection_command.action_clone()

    assert result == 0
    assert (tmp_path / "pkg").is_dir()
    collection_command.lichos_anchor_handler.write.assert_called_once_with(
        host="gitlab.example.com",
        pkg_group="group/pkg",
        branch="main",
        target_dir=Path("pkg"),
    )


def test_action_clone_bare_path_no_host_returns_error(mock_di_container, mock_collection_args):
    """Test that clone with a bare group path fails when no host is configured."""
    mock_di_container.host = None
    mock_collection_args.action = "clone"
    mock_collection_args.target = "group/pkg"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = False

    with patch("lichoscli.commands.collection.UserConfigStore") as mock_store:
        mock_store.read.return_value = {}
        cmd = CollectionCommand(mock_di_container, mock_collection_args)
        result = cmd.action_clone()

    assert result == 1


def test_action_clone_url_dry_run(collection_command, mock_collection_args, tmp_path, monkeypatch):
    """Test that dry run with URL writes nothing."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.dry = True
    mock_collection_args.clone_all = False
    monkeypatch.chdir(tmp_path)

    result = collection_command.action_clone()

    assert result == 0
    collection_command.lichos_anchor_handler.write.assert_not_called()


def test_action_clone_url_all_clones_packages(collection_command, mock_collection_args, tmp_path, monkeypatch, mock_di_container):
    """Test that clone with URL and --all clones packages and writes anchor."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = True
    mock_collection_args.branch = "main"
    packages = [_make_package("pkg-a"), _make_package("pkg-b")]
    mock_di_container.package_service.get_all_packages.return_value = packages
    monkeypatch.chdir(tmp_path)

    with patch("lichoscli.commands.collection.Repo") as mock_repo:
        result = collection_command.action_clone()

    assert result == 0
    assert mock_repo.clone_from.call_count == 2
    # Packages cloned inside the distro directory
    call_urls = [c[0][1] for c in mock_repo.clone_from.call_args_list]
    assert all("my-group" in u for u in call_urls)
    collection_command.lichos_anchor_handler.write.assert_called_once_with(
        host="gitlab.example.com",
        pkg_group="my-org/my-group",
        branch="main",
        target_dir=Path("my-group"),
    )


def test_action_clone_all_no_packages_returns_error(collection_command, mock_collection_args, tmp_path, monkeypatch, mock_di_container):
    """Test that action_clone --all returns 1 when no packages are found."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = True
    mock_di_container.package_service.get_all_packages.return_value = []
    monkeypatch.chdir(tmp_path)

    result = collection_command.action_clone()

    assert result == 1


def test_action_clone_skips_existing_directory(collection_command, mock_collection_args, tmp_path, monkeypatch, mock_di_container):
    """Test that package directories that already exist are skipped (with --all)."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = True
    mock_collection_args.branch = None
    monkeypatch.chdir(tmp_path)
    # Pre-create the package dir inside where the distro dir will be
    (tmp_path / "my-group" / "pkg-a").mkdir(parents=True)

    packages = [_make_package("pkg-a"), _make_package("pkg-b")]
    mock_di_container.package_service.get_all_packages.return_value = packages

    with patch("lichoscli.commands.collection.Repo") as mock_repo:
        result = collection_command.action_clone()

    assert result == 0
    assert mock_repo.clone_from.call_count == 1
    call_args = mock_repo.clone_from.call_args
    assert call_args[0][1].endswith("pkg-b")


def test_action_clone_branch_fallback(collection_command, mock_collection_args, tmp_path, monkeypatch, mock_di_container):
    """Test that a failing branch clone falls back to the default branch."""
    from git.exc import GitCommandError

    mock_collection_args.action = "clone"
    mock_collection_args.target = "https://gitlab.example.com/my-org/my-group"
    mock_collection_args.dry = False
    mock_collection_args.clone_all = True
    mock_collection_args.branch = "feature/missing"
    monkeypatch.chdir(tmp_path)

    packages = [_make_package("pkg-a", default_branch="main")]
    mock_di_container.package_service.get_all_packages.return_value = packages

    with patch("lichoscli.commands.collection.Repo") as mock_repo:
        mock_repo.clone_from.side_effect = [
            GitCommandError("clone", 128),
            MagicMock(),
        ]
        result = collection_command.action_clone()

    assert result == 0
    assert mock_repo.clone_from.call_count == 2


# ------------------------------------------------------------------
# action_clone — no-target listing flow
# ------------------------------------------------------------------

def test_action_clone_no_target_lists_groups(collection_command, mock_collection_args, mock_di_container):
    """Test that clone without a target lists available groups."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = None
    mock_di_container.pkg_group_discovery.search_pkg_groups.return_value = [
        "my-org/my-group", "other-org/other-group"
    ]

    result = collection_command.action_clone()

    assert result == 0
    mock_di_container.pkg_group_discovery.search_pkg_groups.assert_called_once()


def test_action_clone_no_target_no_groups_returns_zero(collection_command, mock_collection_args, mock_di_container):
    """Test that clone without target shows warning and returns 0 when no groups found."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = None
    mock_di_container.pkg_group_discovery.search_pkg_groups.return_value = []

    result = collection_command.action_clone()

    assert result == 0


def test_action_clone_no_target_no_host_returns_error(collection_command, mock_collection_args):
    """Test that clone without target returns error when no host is configured."""
    mock_collection_args.action = "clone"
    mock_collection_args.target = None
    collection_command.di_container.host = None

    with patch("lichoscli.commands.collection.UserConfigStore") as mock_store:
        mock_store.read.return_value = {}
        result = collection_command.action_clone()

    assert result == 1

