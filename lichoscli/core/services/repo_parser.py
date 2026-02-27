# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import os
import re
from typing import Dict, List, Optional
from ..models.repo_package import RepoPackage

LICHOS_VERSION_PATTERN = re.compile(r"lichos\d+")

class RepoParserService:

    def parse_repo_file(self, filepath: str) -> List[RepoPackage]:
        packages = []
        repository_url = "unknown"

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return []

        lines = content.split("\n")
        current_package_dict = {}
        current_field = None

        for line in lines:
            original_line = line
            line = line.strip()

            if line.startswith("# Repository URL:"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    repository_url = parts[1].strip()
                continue

            if not line or line.startswith("#"):
                continue

            if line.startswith("Package:"):
                if current_package_dict:
                    pkg = self._create_package_from_entry(current_package_dict, repository_url)
                    if pkg:
                        packages.append(pkg)

                parts = line.split(":", 1)
                if len(parts) > 1:
                    current_package_dict = {"Package": parts[1].strip()}
                    current_field = "Package"

            elif ":" in line and current_package_dict and not original_line.startswith((" ", "\t")):
                parts = line.split(":", 1)
                key, value = parts[0].strip(), parts[1].strip()
                current_field = key
                current_package_dict[current_field] = value

            elif current_package_dict and current_field and original_line.startswith((" ", "\t")):
                current_package_dict[current_field] += " " + line

        if current_package_dict:
            pkg = self._create_package_from_entry(current_package_dict, repository_url)
            if pkg:
                packages.append(pkg)

        return packages

    def parse_target_packages_file(self, packages_file: str) -> List[RepoPackage]:
        if not os.path.exists(packages_file):
            return []

        installed_packages = []

        try:
            with open(packages_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split("|")
                    if len(parts) >= 4:
                        installed_packages.append(
                            RepoPackage(
                                binary_name=parts[2].split(":")[0],
                                source_name=parts[0],
                                binary_version=parts[3],
                                repository="unknown",
                                is_lichos_package=False,
                                source_version=parts[1],
                            )
                        )
        except OSError:
            return []

        return installed_packages

    def parse_packages_from_dir(self, repos_dir: str) -> Dict[str, RepoPackage]:
        if not os.path.exists(repos_dir) or not os.path.isdir(repos_dir):
            return {}

        package_lookup = {}
        try:
            repo_files = [f for f in os.listdir(repos_dir) if os.path.isfile(os.path.join(repos_dir, f))]
        except OSError:
            return {}

        for filename in repo_files:
            filepath = os.path.join(repos_dir, filename)
            packages = self.parse_repo_file(filepath)
            for pkg in packages:
                package_lookup[pkg.unique_key] = pkg

        return package_lookup

    def parse_packages_from_buildinfo(self, buildinfo_path: str) -> tuple[List[RepoPackage], List[RepoPackage]]:
        try:
            with open(buildinfo_path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return [], []

        build_depends_start = content.find("Installed-Build-Depends:")
        if build_depends_start == -1:
            return [], []

        section_start = build_depends_start + len("Installed-Build-Depends:")
        lines = content[section_start:].split("\n")

        dependencies_text = ""
        for i, line in enumerate(lines):
            if i == 0:
                dependencies_text = line.strip()
            elif line.startswith(" "):
                dependencies_text += " " + line.strip()
            else:
                break

        lichos_packages = []
        debian_packages = []

        if dependencies_text:
            for dep in dependencies_text.split(","):
                dep = dep.strip()
                if not dep:
                    continue

                if "(" in dep:
                    pkg_name = dep.split("(")[0].strip()
                    version_part = dep.split("(")[1].split(")")[0].strip()
                    version = version_part[2:] if version_part.startswith("= ") else version_part
                else:
                    pkg_name = dep
                    version = "unknown"

                is_lichos = bool(LICHOS_VERSION_PATTERN.search(version))
                pkg = RepoPackage(
                    binary_name=pkg_name,
                    source_name=pkg_name,
                    binary_version=version,
                    repository="unknown",
                    source_version=version,
                    is_lichos_package=is_lichos,
                )
                (lichos_packages if pkg.is_lichos_package else debian_packages).append(pkg)

        return lichos_packages, debian_packages

    def _create_package_from_entry(self, package_entry: dict[str, str], repository_url: str) -> Optional[RepoPackage]:
        binary_name = package_entry.get("Package", "")
        if not binary_name:
            return None
            
        version = package_entry.get("Version", "")
        source_entry = package_entry.get("Source", binary_name)
        filename = package_entry.get("Filename", "")

        if "(" in source_entry:
            parts = source_entry.split("(")
            source_name = parts[0].strip()
            if ")" in parts[1]:
                source_version = parts[1].split(")")[0].strip()
            else:
                 source_version = version
        else:
            source_name = source_entry
            source_version = version

        is_lichos = bool(LICHOS_VERSION_PATTERN.search(version))
        
        return RepoPackage(
            binary_name=binary_name,
            source_name=source_name,
            binary_version=version,
            repository=repository_url,
            source_version=source_version,
            filename=filename,
            is_lichos_package=is_lichos,
        )
