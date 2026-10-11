# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from types import SimpleNamespace

from lichoscli.commands.changelog import ChangelogCommand
from lichoscli.core.models.git import GitRepo, GitSubmodule, SubmoduleChange
from lichoscli.core.services import SubmoduleService


def submodule(name, sha):
    return GitSubmodule(name, name, sha * 40, f"git@gitlab.example.com:group/{name}.git")


def test_changelog_reports_added_and_removed_submodules(mock_di_container, tmp_path, monkeypatch):
    GitRepo.init(tmp_path)
    monkeypatch.chdir(tmp_path)
    mock_di_container.obtain_ref(SubmoduleService).diff.return_value = [
        SubmoduleChange(None, submodule("added", "b")),
        SubmoduleChange(submodule("removed", "a"), None),
    ]

    report = ChangelogCommand(mock_di_container, SimpleNamespace(tag="v1", issue_url=None)).generate_changelog()

    assert "#### added\n\n*Added at [bbbbbbbb](https://gitlab.example.com/group/added/-/tree/" in report
    assert "#### removed\n\n*Removed at [aaaaaaaa](https://gitlab.example.com/group/removed/-/tree/" in report
