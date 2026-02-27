# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from dataclasses import dataclass

@dataclass
class RepoPackage:
    binary_name: str
    source_name: str
    binary_version: str
    repository: str
    source_version: str
    filename: str = ""
    is_lichos_package: bool = False

    @property
    def unique_key(self) -> str:
        return f"{self.binary_name}:{self.binary_version}"
