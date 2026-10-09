# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Tests for locating buildinfo files in publish job artifacts."""

import os
import tempfile
import unittest
from unittest.mock import Mock

from lichoscli.providers.gitlab.services.buildinfo_service import GitLabBuildInfoService

BUILDINFO = "Format: 1.0\nSource: signing-container\n"


class TestFindBuildInfoInArtifacts(unittest.TestCase):
    def setUp(self):
        self.service = GitLabBuildInfoService(Mock())
        self.artifacts = tempfile.TemporaryDirectory()
        self.addCleanup(self.artifacts.cleanup)

    def _write_artifact(self, relative_path, content=BUILDINFO):
        path = os.path.join(self.artifacts.name, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as artifact:
            artifact.write(content)

    def test_oci_layout_is_found(self):
        """OCI projects must expose their buildinfo under oci/<arch>/."""
        self._write_artifact("oci/arm64/signing-container-arm64.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertEqual(found, BUILDINFO)

    def test_oci_buildinfo_of_other_architecture_is_ignored(self):
        """Buildinfo lookup must stay architecture specific."""
        self._write_artifact("oci/amd64/signing-container-amd64.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertIsNone(found)

    def test_gbp_layout_is_found(self):
        """Packages must expose their buildinfo under gbp/<arch>/."""
        self._write_artifact("gbp/arm64/lichos-signtool_1.0_arm64.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertEqual(found, BUILDINFO)

    def test_gbp_buildinfo_of_other_architecture_is_ignored(self):
        """Package buildinfo lookup must stay architecture specific."""
        self._write_artifact("gbp/amd64/lichos-signtool_1.0_amd64.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertIsNone(found)

    def test_architecture_independent_buildinfo_is_the_fallback(self):
        """An architecture-independent build must resolve for every architecture."""
        self._write_artifact("gbp/all/lichos-signtool_1.0_all.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertEqual(found, BUILDINFO)

    def test_architecture_specific_buildinfo_wins_over_all(self):
        """The buildinfo of the requested architecture must be preferred over the all/ one."""
        self._write_artifact("gbp/all/lichos-signtool_1.0_all.buildinfo", "Source: all\n")
        self._write_artifact("gbp/arm64/lichos-signtool_1.0_arm64.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertEqual(found, BUILDINFO)

    def test_legacy_gbp_layout_is_still_found(self):
        """Pipelines published before the gbp/<arch>/ layout must still resolve."""
        self._write_artifact("gbp/lichos-signtool_1.0_arm64.buildinfo")

        found = self.service._find_buildinfo_in_artifacts(self.artifacts.name, "arm64")

        self.assertEqual(found, BUILDINFO)


if __name__ == "__main__":
    unittest.main()
