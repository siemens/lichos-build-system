# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Configuration management for Lichos CLI."""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Tuple

from lichoscli.core.models.git.git_repo import GitRepo

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """Supported provider types."""
    GITLAB = "gitlab"
    GITHUB = "github"


@dataclass
class LichosConfig:
    """Configuration object for Lichos CLI."""
    
    host: Optional[str]
    pkg_group: Optional[str]
    branch: Optional[str]
    provider: ProviderType
    branch_explicitly_provided: bool = False
    dry_run: bool = False
    debug: bool = False
    verbose: bool = False
    dump: bool = False
    
    @classmethod
    def detect_provider(cls, host: Optional[str]) -> ProviderType:
        """Detect provider type from host."""
        if host and "github" in host.lower():
            return ProviderType.GITHUB
        return ProviderType.GITLAB


ConfigSource = Tuple[str, Callable[[], Optional[str]]]


class ConfigBuilder:
    """Builds LichosConfig from various sources (args, env, git repo).

    Each config field is resolved through an ordered chain of sources.
    The first source that returns a non-None value wins.  To add a new
    source, append a ``(name, callable)`` pair to the relevant list in
    ``build()``.
    """

    def __init__(self, args):
        """Initialize with parsed command line arguments."""
        self.args = args
        self._ci_data: Optional[tuple] = None
        self._ci_data_resolved = False
        self._local_data: Optional[tuple] = None
        self._local_data_resolved = False

    @staticmethod
    def _resolve(field: str, sources: list[ConfigSource]) -> Optional[str]:
        """Return the first non-None value from *sources*.

        Each source is a ``(name, callable)`` pair.  The *name* is used
        only for debug logging so operators can tell which source won.
        """
        for name, fn in sources:
            value = fn()
            if value is not None:
                logger.debug("%s resolved from %s: %s", field, name, value)
                return value
        logger.debug("%s: no source provided a value", field)
        return None

    def _ci_root_info(self) -> Optional[tuple]:
        """Lazily detect and cache CI root (00ci) repository info."""
        if not self._ci_data_resolved:
            self._ci_data_resolved = True
            repo = GitRepo.auto_detect()
            if repo:
                logger.debug("Found CI root at %s", repo.path)
                self._ci_data = repo.remote_info
        return self._ci_data

    def _ci_field(self, index: int) -> Optional[str]:
        """Extract a field from cached CI root info by index."""
        data = self._ci_root_info()
        return data[index] if data else None

    def _local_repo_info(self) -> Optional[tuple]:
        """Lazily detect and cache local git repository info.

        When the local repo lives in a subgroup (e.g. ``apps/my-pkg``),
        the URL-parsed group would include the subgroup path.  If a CI
        root (``00ci``) exists we adopt its group instead, because that
        is the authoritative workspace-level group.
        """
        if not self._local_data_resolved:
            self._local_data_resolved = True
            repo = GitRepo(".")
            if repo.is_valid:
                logger.debug("Found local git repo at %s", repo.path)
                data = repo.remote_info
                if data:
                    ci = self._ci_root_info()
                    if ci:
                        # Replace host and group with CI root values so
                        # that subgroup packages resolve to the workspace
                        # root group.
                        data = (ci[0], ci[1], data[2], data[3])
                    self._local_data = data
        return self._local_data

    def _local_field(self, index: int) -> Optional[str]:
        """Extract a field from cached local git repo info by index."""
        data = self._local_repo_info()
        return data[index] if data else None

    def build(self) -> LichosConfig:
        """Build LichosConfig by resolving each field through its source chain.

        Resolution precedence per field:
          host:      CLI arg  ->  CI root (00ci) repo  ->  local git repo
          pkg_group: CLI arg  ->  CI root (00ci) repo  ->  local git repo
          branch:    CLI arg  ->  LICHOS_BRANCH env var  ->  current git repo

        The CI root (00ci) is preferred over the local repo for host and
        pkg_group because packages that live in subgroups (e.g.
        ``apps/my-pkg``) would otherwise resolve ``pkg_group`` to the
        subgroup path instead of the workspace root, causing only a
        subset of packages to be visible.
        """
        host = self._resolve("host", [
            ("cli",        lambda: self.args.host),
            ("ci_root",    lambda: self._ci_field(0)),
            ("local_repo", lambda: self._local_field(0)),
        ])

        pkg_group = self._resolve("pkg_group", [
            ("cli",        lambda: self.args.pkg_group),
            ("ci_root",    lambda: self._ci_field(1)),
            ("local_repo", lambda: self._local_field(1)),
        ])

        branch = self._resolve("branch", [
            ("cli",               lambda: self.args.branch),
            ("env:LICHOS_BRANCH", lambda: os.environ.get("LICHOS_BRANCH")),
            ("git:active_branch", lambda: GitRepo(".").active_branch),
        ])

        provider = LichosConfig.detect_provider(host)

        return LichosConfig(
            host=host,
            pkg_group=pkg_group,
            branch=branch,
            provider=provider,
            branch_explicitly_provided=self.args.branch is not None,
            dry_run=self.args.dry,
            debug=self.args.debug,
            verbose=self.args.verbose,
            dump=self.args.dump,
        )
