# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from urllib.parse import urlparse

from lichoscli.commands.base import Command
from lichoscli.core.config import UserConfigStore
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PkgGroupDiscoveryService
from lichoscli.ui.models import Choice

logger = logging.getLogger(__name__)

_SEARCH_QUERY = "00ci"


class ConfigureCommand(Command):
    """Configure lichoscli: set GitLab host and package group"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)

    def execute(self) -> int:

        current_host = None
        current_pkg_group = None
        current_token = None
        if UserConfigStore.exists():
            existingConfig = UserConfigStore.read()
            current_host = existingConfig.get("host") 
            current_pkg_group = existingConfig.get("pkg_group") 
            current_token = existingConfig.get("token")
            token_status = "set" if current_token else "not set"
            self.output.warning(
                "Existing config: host={0}, pkg_group={1}, token={2}".format(
                    current_host, current_pkg_group, token_status
                )
            )
            self.output.info("Leave fields blank to keep existing values.")
            
        host = self.prompts.text_input("GitLab hostname", default=current_host)
        if not host:
            self.output.error("No hostname provided.")
            return 1

        host = self._normalize_host(host)

        if current_token:
            token_prompt = "GitLab personal access token (leave blank to keep existing)"
        else:
            token_prompt = "GitLab personal access token"

        new_token = self.prompts.secret_input(token_prompt)
        token = new_token or current_token

        UserConfigStore.write(host, current_pkg_group or "", token)
        discovery = self.di_container.obtain_ref(PkgGroupDiscoveryService)
        self.output.info("Searching for pkg groups on {0}...".format(host))
        groups = discovery.search_pkg_groups(_SEARCH_QUERY, host=host)
        if not groups:
            self.output.error(
                "No projects matching '{0}' found on {1}.".format(_SEARCH_QUERY, host)
            )
            return 1

        choices = [Choice(value=g, label=g) for g in groups]
        pkg_group = self.prompts.select_one(
            "Select package group",
            "Choose the group that contains the {0} project:".format(_SEARCH_QUERY),
            choices,
        )

        if pkg_group is None:
            self.output.info("Cancelled.")
            return 0

        if not self.prompts.confirm("Save configuration?", default=True):
            self.output.info("Aborted.")
            return 0

        UserConfigStore.write(host, pkg_group, token)
        self.output.success(
            "Configuration saved to {0}".format(UserConfigStore.config_path())
        )
        return 0

    @staticmethod
    def _normalize_host(host: str) -> str:
        parsed = urlparse(host)
        if parsed.netloc:
            return parsed.netloc
        parsed = urlparse("https://{}".format(host))
        return parsed.netloc or host
