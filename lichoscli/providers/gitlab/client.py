# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
from typing import Optional
from urllib.parse import urlparse
from lichoscli.core.config import UserConfigStore

import gitlab
import yaml

logger = logging.getLogger(__name__)


class GitLabClientFactory:
    """Factory for creating authenticated GitLab clients from environment variables/glab config."""

    def __init__(self, host: Optional[str] = None):
        """
        Initialize the factory.

        Args:
            host: GitLab host URL. If not provided, will try environment variables
                  or fall back to glab config.
        """
        self.host = host

    def create(self) -> gitlab.Gitlab:
        """
        Create and return an authenticated GitLab client.
        """
        env_token = self._get_token_from_env()
        env_host = self._get_host_from_env()

        host_to_use = self.host or env_host
        if env_token and host_to_use:
            return self._init_from_env(env_token, host_to_use)

        config_token, config_host = self._get_token_from_config()
        host_to_use = host_to_use or config_host
        if config_token and host_to_use:
            logger.debug("Using GitLab token from user config for host %s", host_to_use)
            return self._init_from_env(config_token, host_to_use)

        try:
            return self._init_from_glab_config(self.host)
        except (FileNotFoundError, ValueError) as e:
            if host_to_use is None:
                raise ValueError(
                    "GitLab host not found. Please specify --host or run from a git repository with a GitLab remote."
                ) from e
            raise

    def _get_token_from_env(self) -> Optional[str]:
        token = os.getenv("LICHOS_GITLAB_TOKEN")
        if token:
            logger.debug("Using GitLab token from environment variable: LICHOS_GITLAB_TOKEN")
            return token
        return None

    def _get_host_from_env(self) -> Optional[str]:
        host = os.getenv("LICHOS_GITLAB_HOST")
        if host:
            logger.debug("Using GitLab host from environment variable: LICHOS_GITLAB_HOST")
            return host
        return None

    def _get_token_from_config(self) -> tuple[Optional[str], Optional[str]]:
        """Return (token, host) stored in the user config file, or (None, None)."""
        data = UserConfigStore.read()
        return data.get("token"), data.get("host")

    def _init_from_env(self, token: str, host: str) -> gitlab.Gitlab:
        gitlab_url = self._ensure_url_scheme(host)
        try:
            gl = gitlab.Gitlab(url=gitlab_url, private_token=token, api_version="4")
            gl.auth()
            logger.info("Successfully authenticated with GitLab at %s using environment token", gitlab_url)
            return gl
        except gitlab.GitlabAuthenticationError:
            logger.error("Failed to authenticate with GitLab using environment token")
            raise

    def _ensure_url_scheme(self, url: str) -> str:
        """
        Ensure URL has a scheme (https:// if none provided).
        """
        parsed = urlparse(url)
        if not parsed.scheme:
            # If no scheme is present, add https://
            return f"https://{url}"
        return url

    def _init_from_glab_config(self, host: Optional[str] = None) -> gitlab.Gitlab:
        """
        Initialize GitLab client from glab config file.

        Args:
            host: Optional host name to use specific host from config
        """
        try:
            config_path = os.path.expanduser("~/.config/glab-cli/config.yml")
            if not os.path.exists(config_path):
                config_path = os.path.expanduser("~/AppData/Local/glab-cli/config.yml")

            if not os.path.exists(config_path):
                raise FileNotFoundError("glab config not found at {}".format(config_path))

            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            hosts = config.get("hosts", {})
            if not hosts:
                raise ValueError("No hosts found in glab config")

            if host:
                # glab stores keys as bare netloc (e.g. "gitlab.example.com"), but
                # the caller may pass a full URL with scheme and/or trailing slash.
                # Normalise to netloc so the lookup always works.
                host_key = self._host_to_key(host)
                if host_key not in hosts:
                    raise ValueError("Host {} not found in glab config".format(host))
                host_config = hosts[host_key]
                gitlab_url = self._ensure_url_scheme(host_key)
            else:
                host_key = next(iter(hosts))
                host_config = hosts[host_key]
                gitlab_url = self._ensure_url_scheme(host_key)

            gl = gitlab.Gitlab(url=gitlab_url, private_token=host_config.get("token"), api_version="4")

            gl.auth()
            logger.info("Successfully authenticated with GitLab at %s", gitlab_url)
            return gl

        except FileNotFoundError as e:
            logger.error("Config file error: %s", str(e))
            raise
        except yaml.YAMLError as e:
            logger.error("YAML parsing error: %s", str(e))
            raise
        except gitlab.GitlabAuthenticationError:
            logger.error("Failed to authenticate with GitLab")
            raise
        except Exception as e:
            logger.error("Failed to initialize GitLab client: %s", str(e))
            raise

    @staticmethod
    def _host_to_key(host: str) -> str:
        """Normalise a host string to the bare netloc used as a key in glab config.

        Examples::

            "https://gitlab.example.com/"  -> "gitlab.example.com"
            "gitlab.example.com"           -> "gitlab.example.com"
            "https://host:8443/path"     -> "host:8443"
        """
        parsed = urlparse(host)
        if parsed.netloc:
            return parsed.netloc
        parsed = urlparse("https://{}".format(host))
        return parsed.netloc
