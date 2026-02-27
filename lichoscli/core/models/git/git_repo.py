# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Union, Tuple, Dict

from git import Repo, GitCommandError, InvalidGitRepositoryError

from lichoscli.core.models.git.git_url import GitUrl
from lichoscli.utils.constants import CI_PKG

logger = logging.getLogger(__name__)


@dataclass
class GitSubmodule:
    """Model representing a git submodule."""
    name: str
    path: str
    hexsha: str
    url: str


class GitRepo:
    """Model representing a Git repository and its operations."""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path).resolve()
        try:
            self.repo = Repo(str(self.path))
        except InvalidGitRepositoryError:
            self.repo = None

    @property
    def is_valid(self) -> bool:
        """Check if the repository is valid."""
        return self.repo is not None

    @property
    def active_branch(self) -> Optional[str]:
        """Get current branch name."""
        if not self.is_valid:
            return None
        try:
            return self.repo.active_branch.name
        except (TypeError, AttributeError):
            return None

    @property
    def has_submodules(self) -> bool:
        """Check if the repository has submodules."""
        if not self.is_valid:
            return False
        try:
            output = self.repo.git.ls_tree("HEAD")
            return "160000 commit" in output
        except GitCommandError:
            return False

    @property
    def submodules(self) -> List[GitSubmodule]:
        """Get list of submodules."""
        if not self.is_valid:
            return []
        try:
            return [
                GitSubmodule(
                    name=sub.name,
                    path=sub.path,
                    hexsha=sub.hexsha,
                    url=sub.url
                )
                for sub in self.repo.submodules
            ]
        except (GitCommandError, ValueError, AttributeError):
            return []

    @classmethod
    def clone_from(cls, url: str, to_path: Union[str, Path], branch: str = "main") -> "GitRepo":
        """Clone a repository."""
        try:
            Repo.clone_from(url, to_path, branch=branch)
            return cls(to_path)
        except GitCommandError as e:
            logger.error("Failed to clone repository from %s: %s", url, e)
            raise

    @classmethod
    def get_or_clone(cls, location: str, branch: str = "main") -> Optional["GitRepo"]:
        """Get existing repository or clone from URL if it doesn't exist locally.
        
        Args:
            location: Either a local path to an existing repo or a URL to clone from
            branch: Branch to checkout/clone
            
        Returns:
            GitRepo instance if successful, None otherwise
        """
        path = Path(location)
        
        # Check if it's a local path
        if path.exists() and path.is_dir():
            repo = cls(path)
            if not repo.is_valid:
                logger.error("Invalid git repository at %s", location)
                return None
                
            # Checkout the desired branch if needed
            if repo.active_branch != branch:
                logger.info("Checking out branch %s", branch)
                if not repo.checkout(branch):
                    logger.error("Failed to checkout branch %s", branch)
                    return None
                repo.pull()
            return repo
        
        # Clone from URL to temporary directory
        temp_dir = tempfile.mkdtemp()
        logger.info("Cloning %s to %s", location, temp_dir)
        try:
            return cls.clone_from(location, temp_dir, branch=branch)
        except GitCommandError as e:
            logger.error("Failed to clone repo: %s", e)
            return None

    @classmethod
    def init(cls, path: Union[str, Path], initial_branch: str = "main", origin_url: Optional[str] = None) -> "GitRepo":
        """Initialize a new repository."""
        path = Path(path)
        repo = Repo.init(str(path), initial_branch=initial_branch)
        
        if origin_url:
            try:
                repo.create_remote("origin", origin_url)
            except GitCommandError as e:
                logger.warning("Failed to add origin remote: %s", e)
        
        return cls(path)

    def checkout(self, branch: str) -> bool:
        """Checkout a specific branch."""
        if not self.is_valid:
            return False
        try:
            if self.active_branch != branch:
                self.repo.git.checkout(branch)
            return True
        except GitCommandError as e:
            logger.error("Failed to checkout branch %s: %s", branch, e)
            return False

    def pull(self) -> bool:
        """Pull changes from remote."""
        if not self.is_valid:
            return False
        try:
            origin = self.repo.remotes.origin
            current_branch = self.repo.active_branch
            
            # Setup tracking if needed (simplified from GitUtils)
            if not current_branch.tracking_branch():
                 remote_branch_name = f"origin/{current_branch.name}"
                 remote_refs = [ref.name for ref in origin.refs]
                 if remote_branch_name in remote_refs:
                     current_branch.set_tracking_branch(origin.refs[current_branch.name])

            origin.pull()
            return True
        except (GitCommandError, AttributeError) as e:
            logger.warning("Failed to pull changes: %s", e)
            return False

    def commit(self, message: str, add_all: bool = True) -> bool:
        """Commit changes."""
        if not self.is_valid:
            return False
        try:
            if add_all:
                self.repo.git.add(A=True)
            
            if not self.repo.is_dirty():
                return False
                
            self.repo.index.commit(message)
            logger.info("Committed changes: %s", message)
            return True
        except GitCommandError as e:
            logger.error("Failed to commit changes: %s", e)
            return False

    def push_branch(self) -> bool:
        """Push current branch to remote."""
        if not self.is_valid:
            return False
        try:
            origin = self.repo.remotes.origin
            current_branch = self.repo.active_branch
            
            if current_branch.tracking_branch():
                origin.push()
            else:
                origin.push(refspec=f"{current_branch.name}:{current_branch.name}", set_upstream=True)
            return True
        except GitCommandError as e:
            logger.error("Failed to push branch: %s", e)
            return False
            
    def push_tags(self) -> bool:
        """Push tags to remote."""
        if not self.is_valid:
            return False
        try:
            origin = self.repo.remotes.origin
            origin.push(tags=True)
            return True
        except GitCommandError as e:
            logger.error("Failed to push tags: %s", e)
            return False

    def create_and_push_tag(self, tag: str, message: str, dry_run: bool = False) -> bool:
        """Create and push a tag."""
        if not self.is_valid:
            return False
        
        if dry_run:
            logger.info("DRY RUN: Would create and push tag %s", tag)
            return True
            
        try:
            existing_tags = [t.name for t in self.repo.tags]
            if tag in existing_tags:
                logger.warning("Tag %s already exists", tag)
                return True
                
            new_tag = self.repo.create_tag(tag, message=message)
            logger.info("Created tag: %s", new_tag.name)
            
            return self.push_tags()
        except GitCommandError as e:
            logger.error("Failed to create/push tag %s: %s", tag, e)
            return False

    def update_submodules(self, init: bool = True, recursive: bool = True) -> bool:
        """Update submodules."""
        if not self.is_valid or not self.has_submodules:
            return True
            
        try:
            args = ["update"]
            if init:
                args.append("--init")
            if recursive:
                args.append("--recursive")
            
            self.repo.git.submodule(*args)
            return True
        except GitCommandError as e:
            logger.error("Failed to update submodules: %s", e)
            return False

    def add_submodule(self, name: str, url: str, path: str, branch: str) -> bool:
        """Add a submodule."""
        if not self.is_valid:
            return False
        try:
            full_path = self.path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            self.repo.create_submodule(
                name=name,
                path=path,
                url=url,
                branch=branch,
                no_checkout=True
            )
            return True
        except GitCommandError as e:
            logger.error("Failed to add submodule %s: %s", name, e)
            return False

    def update_submodule_commit(self, submodule_path: str, commit_sha: str) -> bool:
        """Update a submodule to a specific commit SHA."""
        if not self.is_valid:
            return False
        try:
            self.repo.git.update_index(
                "--add",
                "--cacheinfo",
                "160000",
                commit_sha,
                submodule_path
            )
            return True
        except GitCommandError as e:
            logger.error("Failed to update submodule %s index: %s", submodule_path, e)
            return False

    def get_tags(self) -> List[str]:
        """Get all tags sorted by creation date (newest first)."""
        if not self.is_valid:
            return []
        try:
            return self.repo.git.tag("--sort=-creatordate").splitlines()
        except GitCommandError:
            return []

    def get_last_tag(self) -> str:
        """Get the last tag in the repository."""
        if not self.is_valid:
            return ""
        try:
            return self.repo.git.describe("--tags", "--abbrev=0")
        except GitCommandError:
            # If no tags exist, use the first commit
            try:
                return self.repo.git.rev_list("--max-parents=0", "HEAD")
            except GitCommandError:
                return ""

    def get_remote_url(self) -> str:
        """Get the remote URL for the repository."""
        if not self.is_valid:
            return ""
        try:
            return self.repo.remotes.origin.url
        except (GitCommandError, AttributeError):
            try:
                return self.repo.git.config("--get", "remote.origin.url")
            except GitCommandError:
                return ""


    def get_commit_details(self, sha: str) -> Tuple[str, str]:
        """Get commit subject and body."""
        if not self.is_valid:
            return "", ""
        try:
            commit = self.repo.commit(sha)
            return commit.summary, commit.message
        except (GitCommandError, ValueError):
            return "", ""

    def get_commit_log(self, from_ref: str, to_ref: str = "HEAD", no_merges: bool = False) -> List[str]:
        """Get commit log between two references."""
        if not self.is_valid:
            return []
        try:
            kwargs = {}
            if no_merges:
                kwargs['no_merges'] = True
            logger.info(f"Repository path: {self.path}")
            logger.info(f"Getting commit log from {from_ref} to {to_ref}, no_merges={no_merges}")
            commits = list(self.repo.iter_commits(f"{from_ref}..{to_ref}", **kwargs))
            return [commit.hexsha for commit in commits]
        except (GitCommandError, ValueError):
            return []

    def get_submodule_changes(self, from_ref: str, to_ref: str = "HEAD") -> List[Tuple[str, str, str]]:
        """
        Get submodules that changed between two references.
        Returns list of (submodule_path, old_commit, new_commit).
        """
        if not self.is_valid:
            return []
        
        changes = []
        for submodule in self.submodules:
            try:
                old_commit = self.repo.git.ls_tree(from_ref, submodule.path)
                new_commit = self.repo.git.ls_tree(to_ref, submodule.path)

                if old_commit and new_commit:
                    old_hash = old_commit.split()[2]
                    new_hash = new_commit.split()[2]

                    if old_hash != new_hash:
                        changes.append((submodule.path, old_hash, new_hash))
            except GitCommandError:
                continue


        return changes

    @property
    def remote_info(self) -> Optional[Tuple[str, str, str, str]]:
        """Get parsed remote info ``(host, group, package, branch)``."""
        if not self.is_valid:
            return None
        try:
            url = self.repo.remotes.origin.url
            branch = self.repo.active_branch.name
        except (AttributeError, IndexError, TypeError):
            return None

        parsed = GitUrl.parse(url)
        if parsed:
            return (parsed.host, parsed.group, parsed.package, branch)
        return None

    @property
    def group(self) -> str:
        """Get repository group."""
        data = self.remote_info
        return data[1] if data else ""

    @property
    def package_name(self) -> str:
        """Get package name from repository."""
        data = self.remote_info
        return data[2] if data else ""

    @classmethod
    def find_ci_root(cls, start_path: str = ".") -> Optional[Path]:
        """Find the absolute path containing the 00ci directory by searching upward."""
        start = Path(start_path).resolve()
        if not start.exists():
            return None

        for parent in [start] + list(start.parents):
            ci_dir = parent / CI_PKG
            git_dir = ci_dir / ".git"
            if ci_dir.exists() and git_dir.is_dir():
                return ci_dir
        return None

    @classmethod
    def auto_detect(cls, package_name: Optional[str] = None) -> Optional["GitRepo"]:
        """Auto-detect git repository from package name or CI directory."""
        if package_name and os.path.exists(package_name):
            return cls.get_or_clone(package_name)
        
        ci_dir = cls.find_ci_root()
        if ci_dir:
            return cls(ci_dir)
        return None

