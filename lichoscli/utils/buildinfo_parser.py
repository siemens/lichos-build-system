"""Buildinfo file parser for the deb822 .buildinfo format."""

import logging
from typing import Dict, Optional

from lichoscli.core.models import BuildDependency, BuildInfo

logger = logging.getLogger(__name__)


class BuildinfoParser:
    """Parser for the first deb822 paragraph of a buildinfo file."""

    @staticmethod
    def parse(content: str) -> Optional[BuildInfo]:
        """Parse buildinfo content and return BuildInfo object."""
        fields = BuildinfoParser._parse_fields(content)
        if not fields:
            logger.error("Failed to parse buildinfo: no fields found")
            return None

        installed_build_depends: Dict[str, BuildDependency] = {}
        for entry in fields.get("installed-build-depends", "").split(","):
            # Entries look like "name[:arch] (= version)"; buildinfo always pins with "=".
            package, _, version = entry.partition("(")
            name, _, arch = package.strip().partition(":")
            if name:
                installed_build_depends[name] = BuildDependency(
                    package=name, version=version.strip(" =)"), architecture=arch
                )

        return BuildInfo(
            format=fields.get("format", ""),
            source=fields.get("source", "").split(" ")[0],
            binary=fields.get("binary", "").split(),
            architecture=fields.get("architecture", ""),
            version=fields.get("version", ""),
            installed_build_depends=installed_build_depends,
        )

    @staticmethod
    def _parse_fields(content: str) -> Dict[str, str]:
        """Return the first paragraph's fields keyed by lowercase name, continuation lines joined by spaces."""
        fields: Dict[str, str] = {}
        key = None
        for line in content.splitlines():
            if line.startswith("-----BEGIN PGP SIGNED MESSAGE-----") or line.startswith("Hash:"):
                continue
            if not line.strip():
                if fields:
                    break
                continue
            if line[0] in " \t":
                if key:
                    fields[key] += " " + line.strip()
            elif ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                fields[key] = value.strip()
        return fields
