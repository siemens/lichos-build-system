# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from pathlib import Path

from ..exceptions import BranchError, ServiceError, ValidationError
from ..models.git import GitRepo, GitSubmodule, SubmoduleChange
from .workspace import WorkspaceService


class SubmoduleService:
    """Keep a repository's submodules in step with a workspace, without cloning any member."""

    def __init__(self, workspace_service: WorkspaceService):
        self.workspace_service = workspace_service

    def read(self, repo: GitRepo, ref: str) -> dict[str, GitSubmodule]:
        """Get the submodules recorded at a reference, keyed by path."""
        if not repo.repo.head.is_valid():
            return {}
        git = repo.repo.git
        gitlinks = {}
        for record in filter(None, git.ls_tree("-r", "-z", ref).split("\0")):
            metadata, _, path = record.partition("\t")
            mode, _, sha = metadata.split()
            if mode == "160000":
                gitlinks[path] = sha
        if not gitlinks:
            return {}

        # GitPython keeps the quotes around .gitmodules values; git config unquotes them
        config = git.config("--blob", f"{ref}:.gitmodules", "--null", "--list")
        sections: dict[str, dict[str, str]] = {}
        for record in filter(None, config.split("\0")):
            key, _, value = record.partition("\n")
            name, _, field = key.removeprefix("submodule.").rpartition(".")
            sections.setdefault(name, {})[field] = value

        return {
            fields["path"]: GitSubmodule(name, fields["path"], gitlinks[fields["path"]], fields.get("url", ""))
            for name, fields in sections.items()
            if fields.get("path") in gitlinks
        }

    def create(self, path: Path, branch: str, origin_url: str, push: bool = False) -> list[SubmoduleChange]:
        """Create a repository at ``path`` whose submodules are the packages and images of workspace ``branch``.

        Raises:
            ValidationError: If ``path`` already exists
            BranchError: If no package or image has the branch
            ServiceError: If pushing fails
        """
        if path.exists():
            raise ValidationError(f"Project directory '{path}' already exists")
        desired = self._workspace_submodules(branch)
        return self._apply(GitRepo.init(path, branch, origin_url), desired, branch, push)

    def update(self, path: Path, branch: str, push: bool = False) -> list[SubmoduleChange]:
        """Bring the submodules of the repository at ``path`` in step with workspace ``branch``.

        Raises:
            ValidationError: If ``path`` is not a git repository or is checked out on another branch
            BranchError: If no package or image has the branch, which is far more likely a mistyped
                branch than a request to drop every submodule
            ServiceError: If pushing fails
        """
        repo = GitRepo(path)
        if not repo.is_valid:
            raise ValidationError(f"Invalid git repository at {path}")
        if repo.active_branch != branch:
            raise ValidationError(f"{path} is on branch '{repo.active_branch}', not '{branch}'")
        return self._apply(repo, self._workspace_submodules(branch), branch, push)

    def _workspace_submodules(self, branch: str) -> dict[str, GitSubmodule]:
        heads = self.workspace_service.get_workspace_heads(branch)
        if not heads:
            raise BranchError(f"No packages or images have branch '{branch}'")
        return {
            project.name: GitSubmodule(project.name, project.name, sha, project.ssh_url_to_repo)
            for project, sha in heads
        }

    def _apply(
        self, repo: GitRepo, desired: dict[str, GitSubmodule], branch: str, push: bool
    ) -> list[SubmoduleChange]:
        changes = self._compare(self.read(repo, "HEAD"), desired)
        if not changes:
            return []
        self._stage(repo, changes, desired, branch)
        repo.commit(f"Synchronize workspace {branch}", add_all=False)
        if push and not (repo.push_branch() and repo.push_tags()):
            raise ServiceError(f"Failed to push {repo.path} to remote repository")
        return changes

    @staticmethod
    def _compare(old: dict[str, GitSubmodule], new: dict[str, GitSubmodule]) -> list[SubmoduleChange]:
        return [
            SubmoduleChange(old.get(path), new.get(path))
            for path in sorted(old.keys() | new.keys())
            if old.get(path) != new.get(path)
        ]

    @staticmethod
    def _stage(repo: GitRepo, changes: list[SubmoduleChange], desired: dict[str, GitSubmodule], branch: str) -> None:
        git = repo.repo.git
        for change in changes:
            if change.new is None:
                git.rm("--cached", "--quiet", "--", change.path)
            else:
                git.update_index("--add", "--cacheinfo", f"160000,{change.new.hexsha},{change.path}")

        (repo.path / ".gitmodules").write_text(
            "".join(
                f'[submodule "{submodule.name}"]\n'
                f'\tpath = "{submodule.path}"\n'
                f'\turl = "{submodule.url}"\n'
                f'\tbranch = "refs/heads/{branch}"\n'
                for _, submodule in sorted(desired.items())
            ),
            encoding="utf-8",
        )
        git.add(".gitmodules")
