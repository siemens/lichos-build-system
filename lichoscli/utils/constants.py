# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

# Package constants
CI_PKG = "00ci"
BUILD_IMAGE_PKG = "build-image"
SNAPSHOT_PKG = "00snapshot"
CORE_PACKAGES: list[str] = [CI_PKG, BUILD_IMAGE_PKG, SNAPSHOT_PKG]
LICHOS_MARKER = "lmdc-" # lichos-managed-dev-container, to identify our own

# CI constants
CI_DEFAULT_PIPELINE_NAME = "gbp"
CI_IMAGE_PIPELINE_NAME = "image"
CI_OCI_PIPELINE_NAME = "oci"
CI_TEMPLATE = "{name}.yml@{group}/{pkg}"
CI_PUBLISH_JOB_NAME = "publish"
CI_WORKSPACE_JOB_NAME = "workspace-scheduling"

# Scheduler constants
SCHEDULER_REPORT_TITLE = "Scheduler Report for {0}"
