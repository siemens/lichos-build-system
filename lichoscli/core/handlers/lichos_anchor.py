# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""LichosAnchorHandler interface and its filesystem implementation."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

class LichosAnchorHandler:
    """Reads and writes the .lichos anchor file on the local filesystem."""

    ANCHOR_FILENAME = ".lichos"

    def find(self) -> Optional[Path]:
        """Walk upward from CWD until a .lichos file is found."""
        start = Path(".").resolve()
        for candidate in [start] + list(start.parents):
            lichos_file = candidate / self.ANCHOR_FILENAME
            if lichos_file.is_file():
                logger.debug("Found .lichos anchor at %s", lichos_file)
                return lichos_file
        return None

    def read(self) -> Optional[dict]:
        """Find and parse the nearest .lichos file, returning its contents."""
        path = self.find()
        if path is None:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                return data
            logger.debug(".lichos anchor at %s is not a YAML mapping, ignoring", path)
        except (OSError, yaml.YAMLError) as exc:
            logger.debug("Failed to read .lichos anchor at %s: %s", path, exc)
        return None

    def write(self, host: str, pkg_group: str, branch: str, target_dir: Optional[Path] = None) -> None:
        """Write a .lichos anchor file."""
        base = target_dir if target_dir is not None else Path(".")
        lichos_path = base / self.ANCHOR_FILENAME
        data = {"host": host, "pkg_group": pkg_group, "branch": branch}
        with open(lichos_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        logger.info("Created .lichos anchor at %s", lichos_path.resolve())