import logging
from urllib.parse import urlparse
from typing import Optional
import gitlab
import os
import yaml

logger = logging.getLogger(__name__)


class GitLabClientFactory:
    """Factory for creating authenticated GitLab clients from glab config."""

    def __init__(self, host: Optional[str] = None):
        """
        If host is not provided, uses the default host from glab config.
        """
        self.host = host

    def create(self) -> gitlab.Gitlab:
        """
        Create and return an authenticated GitLab client.
        """
        return self._init_from_glab_config(self.host)

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
                raise FileNotFoundError(f"glab config not found at {config_path}")

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            hosts = config.get("hosts", {})
            if not hosts:
                raise ValueError("No hosts found in glab config")

            if host:
                if host not in hosts:
                    raise ValueError(f"Host {host} not found in glab config")
                host_config = hosts[host]
            else:
                host = next(iter(hosts))
                host_config = hosts[host]

            gitlab_url = self._ensure_url_scheme(host)

            gl = gitlab.Gitlab(
                url=gitlab_url, private_token=host_config.get("token"), api_version="4"
            )

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
