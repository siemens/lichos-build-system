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

from lichoscli.core.handlers.lichos_anchor import LichosAnchorHandler
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
    def write(cls, host: str, token: Optional[str] = None) -> None:
        """Persist a token for *host* to the XDG config file."""
        path = cls.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = cls.read()
        hosts: dict = existing.get("hosts", {})
        entry: dict = hosts.get(host, {})
        if token:
            entry["token"] = token
        hosts[host] = entry
        data: dict = {"hosts": hosts}
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        logger.debug("Wrote user config to %s", path)

    @classmethod
    def get_token(cls, host: str) -> Optional[str]:
        """Return the stored token for *host*, or ``None`` if not configured."""
        data = cls.read()
        return data.get("hosts", {}).get(host, {}).get("token")


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
        self._anchor_data: Optional[dict] = None
        self._anchor_data_resolved = False
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

    def _anchor_info(self) -> Optional[dict]:
        """Lazily find the nearest .lichos anchor file."""
        if not self._anchor_data_resolved:
            self._anchor_data_resolved = True
            handler = LichosAnchorHandler()
            self._anchor_data = handler.read()
            if self._anchor_data:
                logger.debug("Found .lichos anchor with host=%s, pkg_group=%s",
                             self._anchor_data.get("host"),
                             self._anchor_data.get("pkg_group"))
        return self._anchor_data

    def _anchor_field(self, key: str) -> Optional[str]:
        """Return a field from the cached .lichos anchor data."""
        data = self._anchor_info()
        return data.get(key) if data else None

    def _local_repo_info(self) -> Optional[tuple]:
        """Lazily detect and cache local git repository info."""
        if not self._local_data_resolved:
            self._local_data_resolved = True
            repo = GitRepo(".")
            if repo.is_valid:
                logger.debug("Found local git repo at %s", repo.path)
                self._local_data = repo.remote_info
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
          host:      CLI arg  ->  .lichos anchor  ->  local git repo
          pkg_group: CLI arg  ->  .lichos anchor  ->  local git repo
          branch:    CLI arg  ->  LICHOS_BRANCH env var  ->  current git branch  ->  .lichos anchor

        The current git branch takes precedence over the anchor's stored branch so
        that working on a feature branch is reflected automatically.  The anchor
        branch acts as a fallback when running outside any git repository.
        """
        host = self._resolve("host", [
            ("cli",        lambda: self.args.host),
            ("anchor",     lambda: self._anchor_field("host")),
            ("local_repo", lambda: self._local_field(0)),
        ])

        pkg_group = self._resolve("pkg_group", [
            ("cli",        lambda: self.args.pkg_group),
            ("anchor",     lambda: self._anchor_field("pkg_group")),
            ("local_repo", lambda: self._local_field(1)),
        ])

        branch = self._resolve("branch", [
            ("cli",               lambda: self.args.branch),
            ("env:LICHOS_BRANCH", lambda: os.environ.get("LICHOS_BRANCH")),
            ("git:active_branch", lambda: GitRepo(".").active_branch),
            ("anchor",            lambda: self._anchor_field("branch")),
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
