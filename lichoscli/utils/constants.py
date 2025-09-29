from typing import List

# Package constants
CI_PKG = "00ci"
BUILD_IMAGE_PKG = "build-image"
CORE_PACKAGES: List[str] = [CI_PKG, BUILD_IMAGE_PKG]

# CI constants
CI_DEFAULT_PIPELINE_NAME = "gbp"
CI_TEMPLATE = "{name}.yml@{group}/{pkg}"
