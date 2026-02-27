# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from typing import Optional


class HierarchyUtils:
    """Handle hierarchy path operations for fork and hierarchy commands"""

    @staticmethod
    def extract_package_subpath(package_path: str, base_hierarchy: str) -> Optional[str]:
        base_prefix = f"{base_hierarchy}/"
        if package_path.startswith(base_prefix):
            full_package_path = package_path[len(base_prefix) :]
            path_parts = full_package_path.split("/")
            if len(path_parts) > 1:
                return "/".join(path_parts[:-1])
        return None
