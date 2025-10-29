import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from git import InvalidGitRepositoryError
from git.exc import GitCommandError, NoSuchPathError
from git.repo import Repo

from .constants import CI_PKG

logger = logging.getLogger(__name__)


class GitUtils:
    """Handle Git repository operations and parsing"""

    @staticmethod
    def get_git_repo(path: str = ".") -> Optional[Repo]:
        """Get git repository object, return None if invalid"""
        try:
            return Repo(path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            return None

    @staticmethod
    def get_branch(repo: Optional[Repo] = None) -> Optional[str]:
        """Get current branch name"""
        if repo is None:
            repo = GitUtils.get_git_repo()

        if repo is None:
            return None

        try:
            return repo.active_branch.name
        except (TypeError, AttributeError):
            return None

    @staticmethod
    def parse_repo_data(
        repo: Optional[Repo] = None,
    ) -> tuple[str, str, str, str] | None:
        """Parse repository data returning (host, group, package, branch)"""
        if repo is None:
            repo = GitUtils.get_git_repo()
        if not repo:
            return None

        try:
            url = repo.remotes.origin.url
            branch = GitUtils.get_branch(repo)
            if not branch:
                return None
        except (AttributeError, IndexError):
            return None

        # Parse SSH or HTTPS URL
        patterns = [
            r"git@(?P<host>[^:]+):(?P<group>.*)/(?P<package>[^/]+?)(\.git)?$",
            r"https?://(?P<host>[^/]+)/(?P<group>.+)/(?P<package>[^/]+?)(\.git)?$",
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return (
                    match.group("host"),
                    match.group("group"),
                    match.group("package"),
                    branch,
                )
        return None

    @staticmethod
    def get_group(repo: Optional[Repo] = None) -> str:
        """Get repository group"""
        data = GitUtils.parse_repo_data(repo)
        return data[1] if data else ""

    @staticmethod
    def get_package_name_from_git_repo(repo: Optional[Repo] = None) -> str:
        """Get package name from repository"""
        data = GitUtils.parse_repo_data(repo)
        return data[2] if data else ""

    @staticmethod
    def find_ci_directory_path(start_path: str) -> Optional[str]:
        """Find the absolute path containing the 00ci directory by searching upward"""
        start = Path(start_path).resolve()
        if not start.exists():
            return None

        for parent in [start] + list(start.parents):
            ci_dir = parent / CI_PKG
            git_dir = ci_dir / ".git"
            if ci_dir.exists() and git_dir.is_dir():
                return str(ci_dir)
        return None

    @staticmethod
    def auto_detect_git_repo(package_name: Optional[str] = None) -> Optional[Repo]:
        """Auto-detect git repository from package name or CI directory"""
        if package_name and os.path.exists(package_name):
            return GitUtils.get_git_repo(package_name)

        ci_dir_path = GitUtils.find_ci_directory_path(".")
        if ci_dir_path:
            return GitUtils.get_git_repo(ci_dir_path)
        return None

    @staticmethod
    def generate_gitlab_comparison_url(
        old_commit: str, new_commit: str, gitlab_host: str, project_path: str, project_id: Optional[str] = None
    ) -> str:
        """
        Generate a GitLab comparison URL between two commits.

        Args:
            old_commit: The old commit SHA
            new_commit: The new commit SHA
            gitlab_host: GitLab host (e.g., 'gitlab.example.com')
            project_path: Project path (e.g., 'your-group/platform-os/pkg/tools/lichoscli')
            project_id: Optional project ID to add as a parameter

        Returns:
            GitLab comparison URL
        """
        base_url = f"https://{gitlab_host}/{project_path}/-/compare/{old_commit}...{new_commit}"

        if project_id:
            base_url += f"?from_project_id={project_id}"

        return base_url

    @staticmethod
    def generate_package_comparison_urls(
        changed_packages: dict[str, tuple[Optional[str], str]],
        project_mapping: dict[str, tuple[str, str, Optional[str]]],
    ) -> dict[str, str]:
        """
        Generate GitLab comparison URLs for packages with changed commits.

        Args:
            changed_packages: Dict mapping package_name -> (old_commit, new_commit)
            project_mapping: Dict mapping package_name -> (gitlab_host, project_path, project_id)

        Returns:
            Dict mapping package names to their comparison URLs
        """
        comparison_urls = {}

        for package_name, (old_commit, new_commit) in changed_packages.items():
            if package_name not in project_mapping:
                continue

            gitlab_host, project_path, project_id = project_mapping[package_name]

            if old_commit and new_commit and old_commit != new_commit:
                comparison_url = GitUtils.generate_gitlab_comparison_url(
                    old_commit, new_commit, gitlab_host, project_path, project_id
                )
                comparison_urls[package_name] = comparison_url
            elif not old_commit and new_commit:
                comparison_url = f"https://{gitlab_host}/{project_path}/-/commit/{new_commit}"
                if project_id:
                    comparison_url += f"?from_project_id={project_id}"
                comparison_urls[package_name] = comparison_url

        return comparison_urls

    @staticmethod
    def generate_package_comparison_urls_from_projects(
        changed_packages: dict[str, tuple],  # (project, old_commit, new_commit)
        gitlab_host: str,
    ) -> dict[str, str]:
        """
        Generate GitLab comparison URLs for packages with changed commits using project info.

        Args:
            changed_packages: Dict mapping package_name -> (project, old_commit, new_commit)
                             where project has path_with_namespace attribute
            gitlab_host: GitLab host URL

        Returns:
            Dict mapping package names to their comparison URLs
        """
        comparison_urls = {}

        for package_name, (project, old_commit, new_commit) in changed_packages.items():
            try:
                project_path = project.path_with_namespace
                project_id = str(project.id) if hasattr(project, "id") else None

                if old_commit and new_commit and old_commit != new_commit:
                    comparison_url = GitUtils.generate_gitlab_comparison_url(
                        old_commit, new_commit, gitlab_host, project_path, project_id
                    )
                    comparison_urls[package_name] = comparison_url
                elif not old_commit and new_commit:
                    comparison_url = f"https://{gitlab_host}/{project_path}/-/commit/{new_commit}"
                    if project_id:
                        comparison_url += f"?from_project_id={project_id}"
                    comparison_urls[package_name] = comparison_url
            except AttributeError:
                continue

        return comparison_urls

    @staticmethod
    def has_submodules(repo: Optional[Repo] = None) -> bool:
        """Check if the repository has submodules"""
        if repo is None:
            repo = GitUtils.get_git_repo()
        if repo is None:
            return False

        try:
            gitmodules_path = os.path.join(repo.working_dir, ".gitmodules")
            return os.path.exists(gitmodules_path)
        except (AttributeError, TypeError, OSError):
            return False

    @staticmethod
    def initialize_submodules(repo: Optional[Repo] = None) -> bool:
        """Initialize and update submodules if they exist"""
        if repo is None:
            repo = GitUtils.get_git_repo()
        if repo is None:
            return False

        if not GitUtils.has_submodules(repo):
            return True

        try:
            logger.info("Initializing and updating submodules...")
            repo.git.submodule("update", "--init", "--recursive", "--depth=1", "--single-branch")
            return True
        except GitCommandError as e:
            logger.error("Failed to initialize submodules: %s", str(e))
            return False

    @staticmethod
    def get_submodules(repo: Repo) -> list:
        """Get list of submodules in the repository"""
        try:
            return list(repo.submodules)
        except GitCommandError:
            return []

    # Utility methods
    @staticmethod
    def delete_main_from_branch_name(branch_name: str) -> str:
        """Convert branch/main to branch/*"""
        if branch_name.endswith("/main"):
            return branch_name[: branch_name.rfind("/")] + "/*"
        return branch_name

    @staticmethod
    def get_ref_slug(branch: str) -> str:
        """Convert branch name to a valid ref slug"""
        return re.sub(r"[^a-z0-9]", "-", branch.lower()).strip("-")[:63]

    @staticmethod
    def validate_repository_path(path: Path) -> Optional[Repo]:
        """Validate that a path contains a valid git repository"""
        if not path.exists() or not path.is_dir():
            return None
        return GitUtils.get_git_repo(str(path))

    @staticmethod
    def initialize_repository(
        project_path: Path,
        initial_branch: str = "main",
        origin_url: Optional[str] = None,
    ) -> Repo:
        """Initialize a new git repository with specified initial branch and optional origin remote"""
        repo = Repo.init(str(project_path), initial_branch=initial_branch)
        logger.info(
            "Initialized git repository in %s with initial branch '%s'",
            project_path,
            initial_branch,
        )

        if origin_url:
            try:
                repo.create_remote("origin", origin_url)
                logger.info("Added origin remote: %s", origin_url)
            except GitCommandError as e:
                logger.error("Failed to add origin remote %s: %s", origin_url, str(e))

        return repo

    # Repository operations
    @staticmethod
    def _setup_tracking_branch(repo: Repo) -> bool:
        """Setup tracking branch if remote branch exists"""
        try:
            origin = repo.remotes.origin
            current_branch = repo.active_branch
            remote_branch_name = f"origin/{current_branch.name}"
            remote_refs = [ref.name for ref in origin.refs]

            if remote_branch_name in remote_refs:
                current_branch.set_tracking_branch(origin.refs[current_branch.name])
                return True
        except (GitCommandError, AttributeError):
            pass
        return False

    @staticmethod
    def _try_pull(repo: Repo) -> bool:
        """Try to pull changes from remote"""
        try:
            origin = repo.remotes.origin
            current_branch = repo.active_branch

            if current_branch.tracking_branch() or GitUtils._setup_tracking_branch(repo):
                origin.pull()
                return True
        except GitCommandError:
            pass
        return False

    @staticmethod
    def _push_to_remote(repo: Repo, tags: bool = False, force: bool = False) -> bool:
        """Core push operation"""
        try:
            origin = repo.remotes.origin
            current_branch = repo.active_branch

            if tags:
                origin.push(tags=True)
            elif current_branch.tracking_branch():
                origin.push(force=force)
            else:
                # Setup upstream for new branch
                refspec = f"{'+'if force else ''}{current_branch.name}:{current_branch.name}"
                origin.push(refspec=refspec, set_upstream=True)
            return True
        except GitCommandError:
            return False

    @staticmethod
    def push_branch(repo: Repo) -> bool:
        """Push current branch to remote with retry logic"""
        # Try direct push first
        if GitUtils._push_to_remote(repo):
            return True

        # Try pull and push again
        if GitUtils._try_pull(repo) and GitUtils._push_to_remote(repo):
            return True

        # Last resort: force push
        if GitUtils._push_to_remote(repo, force=True):
            logger.warning("Force pushed branch after conflicts")
            return True

        logger.error("Failed to push branch")
        return False

    @staticmethod
    def push_tags(repo: Repo) -> bool:
        """Push all tags to remote"""
        if GitUtils._push_to_remote(repo, tags=True):
            return True

        # Try after pull
        if GitUtils._try_pull(repo) and GitUtils._push_to_remote(repo, tags=True):
            return True

        logger.error("Failed to push tags")
        return False

    @staticmethod
    def create_and_push_tag(repo: Repo, tag: str, message: Optional[str] = None, dry_run: bool = False) -> bool:
        """Create and push a git tag"""
        if dry_run:
            logger.info("DRY RUN: Would tag repository with tag %s", tag)
            return True

        try:
            # Check if tag already exists
            existing_tags = [t.name for t in repo.tags]
            if tag in existing_tags:
                logger.warning("Tag %s already exists", tag)
                return True

            # Create the tag
            tag_message = message or f"Release tag {tag}"
            new_tag = repo.create_tag(tag, message=tag_message)
            logger.info("Created tag: %s", new_tag.name)

            # Push the tag
            try:
                origin = repo.remote("origin")
                origin.push(new_tag)
                return True
            except GitCommandError:
                logger.error("Failed to push tag %s", tag)
                return False

        except GitCommandError as e:
            logger.error("Failed to create tag %s: %s", tag, str(e))
            return False

    @staticmethod
    def add_package_as_submodule(
        repo: Repo,
        project_path: Path,
        package_name: str,
        ssh_url: str,
        default_branch: str,
    ) -> bool:
        """Add a package as a submodule to the repository"""
        try:
            submodule_path = project_path / package_name
            submodule_path.parent.mkdir(parents=True, exist_ok=True)

            repo.create_submodule(
                name=package_name,
                path=str(submodule_path.relative_to(project_path)),
                url=ssh_url,
                branch=default_branch,
            )
            logger.info("Added submodule: %s", package_name)
            return True
        except GitCommandError as e:
            logger.error("Failed to add submodule %s: %s", package_name, str(e))
            return False

    @staticmethod
    def commit_changes(repo: Repo, commit_message: str, add_all: bool = True) -> bool:
        """Commit changes to the repository"""
        try:
            if add_all:
                repo.git.add(A=True)

            if not repo.is_dirty():
                return False

            repo.index.commit(commit_message)
            logger.info("Committed changes: %s", commit_message)
            return True
        except GitCommandError as e:
            logger.error("Failed to commit changes: %s", str(e))
            return False

    @staticmethod
    def commit_submodules_file(repo: Repo, commit_message: str = "Initial commit: Add all pkg submodules") -> bool:
        """Commit the .gitmodules file"""
        try:
            repo.index.add([".gitmodules"])
            repo.index.commit(commit_message)
            logger.info("Created initial commit: %s", commit_message)
            return True
        except GitCommandError as e:
            logger.error("Failed to create initial commit: %s", str(e))
            return False

    @staticmethod
    def push_changes_and_tags(repo: Repo) -> bool:
        """Push all changes and tags to the remote repository"""
        branch_success = GitUtils.push_branch(repo)
        tags_success = GitUtils.push_tags(repo)

        if branch_success and tags_success:
            logger.info("Changes and tags pushed successfully")
            return True
        logger.error("Failed to push changes and/or tags")
        return False

    @staticmethod
    def update_submodule_to_commit(repo: Repo, submodule, new_sha: str) -> bool:
        """Update submodule reference to a specific commit SHA using direct git command"""
        logger.info("Updating submodule %s to %s (direct)", submodule.path, new_sha)

        try:
            subprocess.run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    "160000",
                    new_sha,
                    submodule.path,
                ],
                cwd=repo.working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Failed to update submodule %s: %s", submodule.path, e.stderr)
            return False

    @staticmethod
    def update_submodule_with_latest_commit(repo: Repo, submodule, pkg_group_handler, branch: str) -> bool:
        current_sha = submodule.hexsha

        package = pkg_group_handler.get_package(submodule.name)
        if not package:
            logger.error("Package '%s' not found in hierarchy", submodule.name)
            return False

        branch_obj = pkg_group_handler.get_package_branch(package, branch)
        if not branch_obj:
            logger.error("Branch '%s' not found for package '%s'", branch, package.name)
            return False

        latest_sha = branch_obj.commit["id"]

        if current_sha == latest_sha:
            return False

        success = GitUtils.update_submodule_to_commit(repo, submodule, latest_sha)

        if success:
            logger.info(
                "Updated submodule '%s': %s -> %s",
                submodule.name,
                current_sha[:8],
                latest_sha[:8],
            )
            return True
        logger.error("Failed to update submodule '%s'", submodule.name)
        return False
