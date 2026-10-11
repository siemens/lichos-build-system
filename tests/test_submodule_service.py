# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

import pytest

from lichoscli.core.exceptions import BranchError, ServiceError, ValidationError
from lichoscli.core.models.git import GitRepo
from lichoscli.core.services import SubmoduleService, WorkspaceService

BRANCH = "feature/flocken"


def head(name, sha):
    project = Mock()
    project.name = name
    project.ssh_url_to_repo = f"git@gitlab.example.com:group/{name}.git"
    return project, sha * 40


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.fixture
def workspace_service():
    return Mock(spec=WorkspaceService)


@pytest.fixture
def service(workspace_service):
    return SubmoduleService(workspace_service)


@pytest.fixture
def repo(tmp_path):
    return GitRepo.init(tmp_path / "snapshot", BRANCH)


def update(service, workspace_service, repo, *heads):
    workspace_service.get_workspace_heads.return_value = list(heads)
    return service.update(repo.path, BRANCH)


def hexshas(service, repo, ref="HEAD"):
    return {path: submodule.hexsha for path, submodule in service.read(repo, ref).items()}


def test_create_records_workspace_heads_without_cloning(service, workspace_service, tmp_path):
    workspace_service.get_workspace_heads.return_value = [head("image-qemu", "b"), head("package-a", "a")]

    service.create(tmp_path / "snapshot", BRANCH, "git@gitlab.example.com:group/snapshot.git")
    repo = GitRepo(tmp_path / "snapshot")

    assert hexshas(service, repo) == {"image-qemu": "b" * 40, "package-a": "a" * 40}
    assert not (repo.path / ".git" / "modules").exists()
    assert 'branch = "refs/heads/feature/flocken"' in (repo.path / ".gitmodules").read_text()


def test_update_adds_updates_and_removes_members(service, workspace_service, repo):
    update(service, workspace_service, repo, head("package-a", "a"), head("removed", "c"))

    changes = update(service, workspace_service, repo, head("added", "d"), head("package-a", "e"))

    assert [(c.path, c.kind) for c in changes] == [("added", "added"), ("package-a", "updated"), ("removed", "removed")]
    assert hexshas(service, repo) == {"added": "d" * 40, "package-a": "e" * 40}


def test_update_without_changes_creates_no_commit(service, workspace_service, repo):
    update(service, workspace_service, repo, head("package-a", "a"))
    before = repo.repo.head.commit.hexsha

    assert update(service, workspace_service, repo, head("package-a", "a")) == []
    assert repo.repo.head.commit.hexsha == before


def test_update_keeps_members_when_no_package_has_the_branch(service, workspace_service, repo):
    update(service, workspace_service, repo, head("package-a", "a"))

    with pytest.raises(BranchError):
        update(service, workspace_service, repo)

    assert set(service.read(repo, "HEAD")) == {"package-a"}


def test_create_leaves_no_directory_behind_when_no_package_has_the_branch(service, workspace_service, tmp_path):
    workspace_service.get_workspace_heads.return_value = []

    with pytest.raises(BranchError):
        service.create(tmp_path / "snapshot", BRANCH, "git@gitlab.example.com:group/snapshot.git")

    assert not (tmp_path / "snapshot").exists()


def test_create_refuses_an_existing_directory(service, tmp_path):
    with pytest.raises(ValidationError):
        service.create(tmp_path, BRANCH, "git@gitlab.example.com:group/snapshot.git")


def test_update_refuses_a_path_that_is_not_a_repository(service, tmp_path):
    with pytest.raises(ValidationError):
        service.update(tmp_path, BRANCH)


def test_update_refuses_a_repository_on_another_branch(service, workspace_service, tmp_path):
    repo = GitRepo.init(tmp_path / "snapshot", "flocken")
    workspace_service.get_workspace_heads.return_value = [head("package-a", "a")]

    with pytest.raises(ValidationError):
        service.update(repo.path, BRANCH)

    workspace_service.get_workspace_heads.assert_not_called()


def test_update_fails_when_the_push_fails(service, workspace_service, repo, tmp_path):
    repo.repo.create_remote("origin", str(tmp_path / "unreachable.git"))
    workspace_service.get_workspace_heads.return_value = [head("package-a", "a")]

    with pytest.raises(ServiceError):
        service.update(repo.path, BRANCH, push=True)


def test_diff_compares_the_requested_references(service, workspace_service, repo):
    update(service, workspace_service, repo, head("removed", "a"))
    old = repo.repo.head.commit.hexsha
    update(service, workspace_service, repo, head("added", "b"))
    new = repo.repo.head.commit.hexsha
    update(service, workspace_service, repo, head("unrelated", "c"))

    assert [(c.path, c.kind) for c in service.diff(repo, old, new)] == [("added", "added"), ("removed", "removed")]


def test_read_unquotes_gitmodules_values(service, repo):
    (repo.path / ".gitmodules").write_text(
        '[submodule "package-a"]\n\tpath = "package-a"\n\turl = "git@gitlab.example.com:group/package-a.git"\n'
    )
    repo.repo.git.update_index("--add", "--cacheinfo", f"160000,{'a' * 40},package-a")
    repo.repo.git.add(".gitmodules")
    repo.repo.git.commit("-m", "snapshot")

    submodule = service.read(repo, "HEAD")["package-a"]

    assert (submodule.name, submodule.url) == ("package-a", "git@gitlab.example.com:group/package-a.git")
