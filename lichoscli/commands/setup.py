# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from urllib.parse import urlparse

from lichoscli.commands.base import Command
from lichoscli.core.config import UserConfigStore

logger = logging.getLogger(__name__)


class SetupCommand(Command):
    """Configure lichoscli (GitLab host and personal access token)"""

    def execute(self) -> int:
        known_hosts = list(UserConfigStore.read().get("hosts", {}).keys())
        if known_hosts:
            self.output.info("Configured hosts: {}".format(", ".join(known_hosts)))

        host = self.prompts.text_input("GitLab hostname")
        if not host:
            self.output.error("No hostname provided.")
            return 1
        host = self._normalize_host(host)

        existing_token = UserConfigStore.get_token(host)
        if existing_token:
            token_prompt = "GitLab personal access token (leave blank to keep existing)"
        else:
            token_prompt = "GitLab personal access token"
        new_token = self.prompts.secret_input(token_prompt)
        token = new_token or existing_token

        UserConfigStore.write(host, token)

        self.output.success("Configuration saved to {}.".format(UserConfigStore.config_path()))
        return 0

    def _normalize_host(self, host: str) -> str:
        """Strip scheme from host if provided as a URL."""
        parsed = urlparse(host)
        if parsed.netloc:
            return parsed.netloc
        parsed = urlparse("https://{}".format(host))
        return parsed.netloc or host
