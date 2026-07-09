# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
from urllib.parse import urlparse

from lichoscli.commands.base import Command
from lichoscli.core.config import ContainerRuntime, UserConfigStore
from lichoscli.ui import Choice

logger = logging.getLogger(__name__)


class SetupCommand(Command):
    """Configure lichoscli (GitLab host, personal access token, container runtime)"""

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

        self._prompt_container_runtime()
        self.output.success(f"Configuration saved to {UserConfigStore.config_path()}.")
        return 0

    def _prompt_container_runtime(self) -> None:
        """Ask the user which OCI container runtime to use, defaulting to docker."""
        stored = UserConfigStore.get_container_runtime()
        try:
            default_runtime = ContainerRuntime(stored) if stored else ContainerRuntime.DOCKER
        except ValueError:
            default_runtime = ContainerRuntime.DOCKER

        choices = [
            Choice(ContainerRuntime.DOCKER.value, "docker (default)"),
            Choice(ContainerRuntime.PODMAN.value, "podman"),
        ]
        selected = self.prompts.select_one(
            "Container runtime",
            "Which OCI runtime should lichoscli use to run build containers?",
            choices,
        )
        runtime = selected or default_runtime.value
        UserConfigStore.set_container_runtime(runtime)
        self.output.info(f"Container runtime set to {runtime}.")

    def _normalize_host(self, host: str) -> str:
        """Strip scheme from host if provided as a URL."""
        parsed = urlparse(host)
        if parsed.netloc:
            return parsed.netloc
        parsed = urlparse(f"https://{host}")
        return parsed.netloc or host
