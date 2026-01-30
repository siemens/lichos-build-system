"""GitLab Project model wrapper."""

import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from gitlab import GitlabError
from gitlab.v4.objects import Project as GitLabProjectObject

from lichoscli.core.models import Project
from lichoscli.utils import CIConfigUtils
from lichoscli.utils.cache_decorators import CacheMixin, cached_property
from lichoscli.utils.constants import CI_DEFAULT_PIPELINE_NAME

from .merge_requests import GitLabMergeRequests
from .pipelines import GitLabPipelines
from .tags import GitLabTags
from .variables import GitLabVariables

if TYPE_CHECKING:
    from lichoscli.core.models import MergeRequests, Pipelines, Tags, Variables

logger = logging.getLogger(__name__)


class GitLabProject(Project, CacheMixin):
    """Wrapper for GitLab Project objects."""

    def __init__(self, gitlab_project: GitLabProjectObject):
        self._project = gitlab_project
        self._variables: Optional[Variables] = None
        self._tags: Optional[Tags] = None
        self._pipelines: Optional[Pipelines] = None
        self._merge_requests: Optional[MergeRequests] = None

    @property
    def id(self) -> int:
        return self._project.id

    @property
    def path(self) -> str:
        return self._project.path

    @property
    def name(self) -> str:
        return self._project.name

    @property
    def path_with_namespace(self) -> str:
        return self._project.path_with_namespace

    @property
    def web_url(self) -> str:
        return self._project.web_url

    @property
    def default_branch(self) -> str:
        return self._project.default_branch

    @default_branch.setter
    def default_branch(self, value: str) -> None:
        self._project.default_branch = value

    @property
    def ci_config_path(self) -> Optional[str]:
        return getattr(self._project, "ci_config_path", None)

    @ci_config_path.setter
    def ci_config_path(self, value: str) -> None:
        self._project.ci_config_path = value

    @property
    def archived(self) -> bool:
        return getattr(self._project, "archived", False)

    @property
    def builds_access_level(self) -> Optional[str]:
        return getattr(self._project, "builds_access_level", None)

    @builds_access_level.setter
    def builds_access_level(self, value: str) -> None:
        self._project.builds_access_level = value

    @property
    def ssh_url_to_repo(self) -> str:
        return self._project.ssh_url_to_repo

    @property
    def is_fork(self) -> bool:
        """Whether this project is a fork of another project."""
        forked_from = getattr(self._project, "forked_from_project", None)
        return forked_from is not None

    @property
    def parent_project_namespace(self) -> Optional[str]:
        """The full namespace path of the parent project if this is a fork."""
        forked_from = getattr(self._project, "forked_from_project", None)
        if forked_from and isinstance(forked_from, dict):
            namespace = forked_from.get("namespace", {})
            if isinstance(namespace, dict):
                return namespace.get("full_path")
        return None

    @property
    def parent_ssh_url_to_repo(self) -> Optional[str]:
        """SSH URL of the parent project if this is a fork, None otherwise."""
        forked_from = getattr(self._project, "forked_from_project", None)
        if forked_from and isinstance(forked_from, dict):
            return forked_from.get("ssh_url_to_repo")
        return None

    @property
    def is_package(self) -> bool:
        """Check if the project is a package."""
        if not self.ci_config_path:
            return False

        parsed = CIConfigUtils.parse_ci_config_path(self.ci_config_path)
        return parsed is not None and parsed.name == CI_DEFAULT_PIPELINE_NAME

    @property
    def is_image(self) -> bool:
        """Check if the project is an image."""
        if not self.ci_config_path:
            return False

        parsed = CIConfigUtils.parse_ci_config_path(self.ci_config_path)
        return parsed is not None and parsed.name == "image"

    @property
    def attributes(self) -> dict[str, Any]:
        return getattr(self._project, "attributes", {})

    @property
    def namespace(self) -> dict[str, Any]:
        return getattr(self._project, "namespace", {})

    @property
    def variables(self) -> "Variables":
        """Project variables collection."""
        if self._variables is None:
            self._variables = GitLabVariables(self._project)
        return self._variables

    @cached_property("branches", ttl=300)
    @property
    def branches(self):
        """Project branches collection with caching."""
        return self._project.branches

    @cached_property("protectedbranches", ttl=300)
    @property
    def protectedbranches(self):
        """Project protected branches manager with caching."""
        return self._project.protectedbranches

    @property
    def tags(self) -> "Tags":
        """Project tags collection."""
        if self._tags is None:
            self._tags = GitLabTags(self._project)
        return self._tags

    @property
    def pipelines(self) -> "Pipelines":
        """Project pipelines collection."""
        if self._pipelines is None:
            self._pipelines = GitLabPipelines(self._project, self)
        return self._pipelines

    @property
    def merge_requests(self) -> "MergeRequests":
        """Project merge requests collection."""
        if self._merge_requests is None:
            self._merge_requests = GitLabMergeRequests(self._project)
        return self._merge_requests

    @cached_property("mergerequests", ttl=300)
    @property
    def mergerequests(self):
        """Project merge requests manager with caching."""
        return self._project.mergerequests

    @cached_property("forks", ttl=300)
    @property
    def forks(self):
        """Project forks collection with caching."""
        return self._project.forks

    def has_branch(self, branch_name: str) -> bool:
        """Check if the project has a branch with the given name.

        Args:
            branch_name: Name of the branch to check for

        Returns:
            True if the branch exists, False otherwise
        """
        try:
            self._project.branches.get(branch_name)
            return True
        except GitlabError:
            return False

    def save(self):
        """Save changes to the project."""
        return self._project.save()

    def create_fork_relation(self, parent_id: int):
        """Create a fork relationship with a parent project."""
        return self._project.create_fork_relation(parent_id)

    def fork_to(self, target_namespace: str, subgroup: Optional[str] = None) -> Optional["Project"]:
        """Fork this project to a target namespace with optional subgroup.

        Args:
            target_namespace: The namespace path to fork to
            subgroup: Optional subgroup within the target namespace

        Returns:
            The forked project if successful, None otherwise
        """
        from .projects import GitLabProjects

        try:
            target_namespace_path = f"{target_namespace}/{subgroup or ''}".rstrip("/")

            gitlab = self._project.manager.gitlab

            projects_collection = GitLabProjects(target_namespace, gitlab)
            target_group_id = projects_collection.get_group_id(target_namespace_path)

            if not target_group_id:
                if subgroup:
                    logger.info(
                        "Target subgroup '%s' not found, attempting to create it",
                        subgroup,
                    )
                    if projects_collection.create_subgroup(subgroup):
                        target_group_id = projects_collection.get_group_id(target_namespace_path)
                    else:
                        logger.error("Failed to create subgroup '%s'", subgroup)
                        return None

                if not target_group_id:
                    logger.error("Target group '%s' not found", target_namespace_path)
                    return None

            target_namespace_id = target_group_id

            target_projects = GitLabProjects(target_namespace, gitlab)
            existing_package = target_projects.get(self.name)
            if existing_package:
                logger.error(
                    "Package '%s' already exists in target hierarchy '%s'",
                    self.name,
                    target_namespace_path,
                )
                return None

            logger.info(
                "Forking package from %s to %s",
                self.path_with_namespace,
                target_namespace_path,
            )

            fork_data = {
                "namespace_id": target_namespace_id,
                "name": self.name,
                "path": self.name,
            }

            self._project.forks.create(fork_data)

            forked_package = None
            for _ in range(3):
                forked_package = target_projects.get(self.name)
                if forked_package:
                    break
                time.sleep(1)

            if not forked_package:
                logger.error("Fork created but package not found after retries")
                return None

            logger.info("Successfully forked package: %s", forked_package.path_with_namespace)
            return forked_package

        except GitlabError as e:
            logger.error("GitLab API error forking package: %s", str(e))
            return None

    def download_artifacts_by_ref(self, job_name: str, ref_name: str) -> Optional[bytes]:
        """Download artifacts for a specific job and ref (for internal use by artifacts model)."""
        try:
            return self._project.artifacts.download(job=job_name, ref_name=ref_name)
        except GitlabError as e:
            logger.debug(
                "Failed to download artifacts for job %s, ref %s: %s",
                job_name,
                ref_name,
                str(e),
            )
            return None

    def get_commits(self, from_ref: str, to_ref: str) -> list[dict[str, Any]]:
        """Get list of commits between two references using GitLab API."""
        try:
            comparison = self._project.repository_compare(from_ref, to_ref)
            return comparison.get("commits", [])
        except GitlabError as e:
            logger.debug(
                "Failed to get commits between %s and %s for project %s: %s",
                from_ref,
                to_ref,
                self.name,
                str(e),
            )
            return []

    def get_latest_commit_sha(self, branch: str) -> Optional[str]:
        """Get the latest commit SHA for a given branch.

        Args:
            branch: The branch name to get the latest commit SHA from

        Returns:
            The latest commit SHA if successful, None otherwise
        """
        try:
            branch_obj = self.branches.get(branch)
            if (
                branch_obj
                and hasattr(branch_obj, "commit")
                and "id" in branch_obj.commit
            ):
                return branch_obj.commit["id"]
            return None
        except GitlabError as e:
            logger.debug(
                "Failed to get latest commit SHA for branch %s: %s",
                branch,
                str(e),
            )
            return None

    def has_protected_branches_with_push_access(self) -> list[str]:
        """Get list of protected branches that allow direct push access."""

        try:
            protected_branches = self.protectedbranches.list()

            if not protected_branches:
                return []

            branches_with_push = []
            for pb in protected_branches:
                push_access_levels = getattr(pb, 'push_access_levels', None)
                
                if not push_access_levels:
                    # No push_access_levels means push is allowed by default
                    branches_with_push.append(pb.name)
                    continue
                
                for access in push_access_levels:
                    access_level = getattr(access, 'access_level', None)
                    if access_level is None or access_level > 0:
                        branches_with_push.append(pb.name)
                        break

            return branches_with_push
        except GitlabError as e:
            logger.debug("Failed to check protected branch push access: %s", str(e))
            return []
