# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Podman-backed ContainerService implementation."""

import logging

from lichoscli.core.services import ContainerConfig
from lichoscli.providers.container.base import OciContainerService

logger = logging.getLogger(__name__)


class PodmanContainerService(OciContainerService):
    """Podman implementation of ContainerService.

    Podman does not auto-map the calling user's UID into the container the way
    docker does when running rootless, so a build image's pre-existing
    ``builder`` user (uid 1000) would otherwise be unable to write into bind
    mounts owned by the host user. The uidmaps below pin container uid 0 to a
    high host uid (so any process the image itself runs as root sees a writable
    view of the bind mount) and remap container uid 1000 onto the host user,
    making the build directory appear owned by ``builder``.
    """

    _PODMAN_OPTIONS = [
        "--user", "root",
        "--uidmap", "0:1:1",
        "--uidmap", "1000:0:1",
        "--uidmap", "1:2:999",
        "--uidmap", "1001:1001:64535",
        # podman logs all output to journal by default. Not
        # desirable for interactive shells
        "--log-driver", "none",
    ]

    def __init__(self):
        super().__init__(command="podman")

    def build_run_command(self, config: ContainerConfig) -> list[str]:
        """Build the ``podman run`` command, including uid mapping."""
        return self.compose_run_command(config, runtime_options=self._PODMAN_OPTIONS)
