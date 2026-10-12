# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Tests for parsing .buildinfo files."""

import unittest

from lichoscli.core.models import BuildDependency
from lichoscli.utils.buildinfo_parser import BuildinfoParser

BUILDINFO = """-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

Format: 1.0
Source: rauc-config (1.0)
Binary: rauc-config rauc-config-tools
Architecture: all source
Version: 260527.1+lichos0local
Checksums-Sha256:
 648703b2 749 rauc-config_260527.1.dsc
Installed-Build-Depends:
 autoconf (= 2.72-3.1),
 automake (= 1:1.17-4),
 libc6:arm64 (= 2.41-12),
 nover
Environment:
 DEB_BUILD_OPTIONS="parallel=8"

-----BEGIN PGP SIGNATURE-----
Version: ignored
"""


class TestBuildinfoParser(unittest.TestCase):
    def test_parse(self):
        info = BuildinfoParser.parse(BUILDINFO)
        assert info is not None

        self.assertEqual(info.format, "1.0")
        self.assertEqual(info.source, "rauc-config")
        self.assertEqual(info.binary, ["rauc-config", "rauc-config-tools"])
        self.assertEqual(info.architecture, "all source")
        self.assertEqual(info.version, "260527.1+lichos0local")
        self.assertEqual(
            list(info.installed_build_depends.values()),
            [
                BuildDependency("autoconf", "2.72-3.1", ""),
                BuildDependency("automake", "1:1.17-4", ""),
                BuildDependency("libc6", "2.41-12", "arm64"),
                BuildDependency("nover", "", ""),
            ],
        )

    def test_empty_content_returns_none(self):
        self.assertIsNone(BuildinfoParser.parse(""))


if __name__ == "__main__":
    unittest.main()
