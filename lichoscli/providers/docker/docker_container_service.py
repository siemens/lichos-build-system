# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Docker-backed ContainerService implementation."""

import logging

from lichoscli.core.services import ContainerConfig
from lichoscli.providers.container.base import OciContainerService

logger = logging.getLogger(__name__)


class DockerContainerService(OciContainerService):
    """Docker implementation of ContainerService."""

    def __init__(self):
        super().__init__(command="docker")

    def build_run_command(self, config: ContainerConfig) -> list[str]:
        """Build the ``docker run`` command from configuration."""
        return self.compose_run_command(config)
