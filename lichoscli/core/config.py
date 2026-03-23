# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Configuration management for Lichos CLI."""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Tuple, Type

import yaml
from xdg import xdg_config_home

from lichoscli.core.models.git.git_repo import GitRepo
from lichoscli.ui import OutputBackend, PromptBackend

logger = logging.getLogger(__name__)


class UserConfigStore:
    """Read and write user-level lichoscli configuration to the XDG config directory.

    The file is located at ``$XDG_CONFIG_HOME/lichos/config.yml`` which
    typically resolves to ``~/.config/lichos/config.yml``.
    """

    _CONFIG_DIR = "lichos"
    _CONFIG_FILE = "config.yml"

    @classmethod
    def config_path(cls) -> Path:
        """Return the absolute path to the config file."""
        return xdg_config_home() / cls._CONFIG_DIR / cls._CONFIG_FILE

    @classmethod
    def exists(cls) -> bool:
        """Return True if the config file exists."""
        return cls.config_path().exists()

    @classmethod
    def read(cls) -> dict:
        """Read the config file and return its contents as a dict.

        Returns an empty dict when the file does not exist.
        """
        path = cls.config_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            logger.debug("Failed to read user config from %s", path)
            return {}

    @classmethod
    def write(cls, host: str, pkg_group: str, token: Optional[str] = None) -> None:
        """Persist host, pkg_group, and optionally token to the XDG config file."""
        path = cls.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {"host": host, "pkg_group": pkg_group}
        if token:
            data["token"] = token
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        logger.debug("Wrote user config to %s", path)


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
    output_backend: OutputBackend = OutputBackend.TERMINAL
    prompt_backend: PromptBackend = PromptBackend.TERMINAL
    
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
        self._xdg_data: Optional[dict] = None
        self._xdg_data_resolved = False

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

    @staticmethod
    def _resolve_enum(field: str, enum_type: Type[Enum], value: Optional[str], default: Enum) -> Enum:
        if value is None:
            logger.debug("%s defaulted to %s", field, default.value)
            return default

        try:
            enum_value = enum_type(value)
        except ValueError as exc:
            valid_values = ", ".join(member.value for member in enum_type)
            raise ValueError(f"Invalid {field}: {value}. Expected one of: {valid_values}") from exc

        logger.debug("%s resolved to %s", field, enum_value.value)
        return enum_value

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

    def _xdg_config_info(self) -> dict:
        """Lazily read and cache the XDG user config file."""
        if not self._xdg_data_resolved:
            self._xdg_data_resolved = True
            self._xdg_data = UserConfigStore.read()
            if self._xdg_data:
                logger.debug("Found user config at %s", UserConfigStore.config_path())
        return self._xdg_data or {}

    def _xdg_field(self, key: str) -> Optional[str]:
        """Return a field from the cached XDG user config."""
        return self._xdg_config_info().get(key)

    def build(self) -> LichosConfig:
        """Build LichosConfig by resolving each field through its source chain.

        Resolution precedence per field:
          host:      CLI arg  ->  CI root (00ci) repo  ->  local git repo  ->  XDG config file
          pkg_group: CLI arg  ->  CI root (00ci) repo  ->  local git repo  ->  XDG config file
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
            ("xdg_config", lambda: self._xdg_field("host")),
        ])

        pkg_group = self._resolve("pkg_group", [
            ("cli",        lambda: self.args.pkg_group),
            ("ci_root",    lambda: self._ci_field(1)),
            ("local_repo", lambda: self._local_field(1)),
            ("xdg_config", lambda: self._xdg_field("pkg_group")),
        ])

        branch = self._resolve("branch", [
            ("cli",               lambda: self.args.branch),
            ("env:LICHOS_BRANCH", lambda: os.environ.get("LICHOS_BRANCH")),
            ("git:active_branch", lambda: GitRepo(".").active_branch),
        ])

        output_backend = self._resolve_enum(
            "output_backend",
            OutputBackend,
            self._resolve("output_backend", [
                ("cli", lambda: getattr(self.args, "output_backend", None)),
                ("env:LICHOS_OUTPUT_BACKEND", lambda: os.environ.get("LICHOS_OUTPUT_BACKEND")),
            ]),
            OutputBackend.TERMINAL,
        )

        prompt_backend = self._resolve_enum(
            "prompt_backend",
            PromptBackend,
            self._resolve("prompt_backend", [
                ("cli", lambda: getattr(self.args, "prompt_backend", None)),
                ("env:LICHOS_PROMPT_BACKEND", lambda: os.environ.get("LICHOS_PROMPT_BACKEND")),
            ]),
            PromptBackend.TERMINAL,
        )

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
            output_backend=output_backend,
            prompt_backend=prompt_backend,
        )
