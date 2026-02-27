# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Set

import requests

from lichoscli.core.models.repo_package import RepoPackage
from lichoscli.core.services.repo_parser import RepoParserService

logger = logging.getLogger(__name__)


class SourceCollectionService:
    def __init__(self, repo_parser: RepoParserService):
        self.repo_parser = repo_parser

    def download_file(self, url: str, dest_path: str) -> bool:
        try:
            response = requests.get(url, allow_redirects=True, stream=True)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return os.path.getsize(dest_path) > 0
        except (requests.RequestException, OSError):
            pass
        return False

    def download_debian_sources(self, packages: List[RepoPackage], output_dir: str) -> None:
        downloaded_sources = set()
        for package in packages:
            source_key = f"{package.source_name}:{package.source_version}"
            if source_key in downloaded_sources:
                continue

            base_url = f"{package.repository}/{os.path.dirname(package.filename)}"
  
            version_without_epoch = package.source_version.split(':', 1)[-1]
            dsc_filename = f"{package.source_name}_{version_without_epoch}.dsc"
            dsc_url = f"{base_url}/{dsc_filename}"
            dsc_dest_path = os.path.join(output_dir, dsc_filename)

            if self.download_file(dsc_url, dsc_dest_path):
                files_to_download = self._parse_dsc_files(dsc_dest_path)

                for filename in files_to_download:
                    url = f"{base_url}/{filename}"
                    dest_path = os.path.join(output_dir, filename)

                    if not self.download_file(url, dest_path) and os.path.exists(dest_path):
                        os.remove(dest_path)
            
            downloaded_sources.add(source_key)

    def _parse_dsc_files(self, dsc_path: str) -> List[str]:
        files_to_download = []

        try:
            with open(dsc_path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return []

        lines = content.split("\n")
        in_files_section = False

        for line in lines:
            original_line = line
            line = line.strip()

            if line.startswith(("Files:", "Checksums-Sha1:", "Checksums-Sha256:")):
                in_files_section = True
                continue

            if in_files_section:
                if line and not original_line.startswith((" ", "\t")):
                    in_files_section = False
                    continue

                if line and original_line.startswith((" ", "\t")):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        filename = parts[2]
                        if filename not in files_to_download:
                            files_to_download.append(filename)

        return files_to_download

    def download_lichos_sources(self, packages: List[RepoPackage], output_dir: str) -> None:
        downloaded_sources = set()
        for package in packages:
            source_key = f"{package.source_name}:{package.source_version}"
            if source_key in downloaded_sources:
                continue

            base_url = f"{package.repository}/pool/{package.source_name[0]}/{package.source_name}"
            filename = f"{package.source_name}_{package.source_version}_all.deb"
            url = f"{base_url}/{filename}"
            temp_file = os.path.join(output_dir, filename)

            if self.download_file(url, temp_file):
                self._unpack_lichos_source(temp_file, output_dir)
                os.remove(temp_file)
            elif os.path.exists(temp_file):
                os.remove(temp_file)
            
            downloaded_sources.add(source_key)

    def _unpack_lichos_source(self, deb_file: str, output_dir: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                subprocess.run(["dpkg-deb", "-x", deb_file, temp_dir], check=True)

                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        src_file = os.path.join(root, file)
                        dest_file = os.path.join(output_dir, file)
                        shutil.copy2(src_file, dest_file)
            except subprocess.CalledProcessError:
                logger.error("Failed to unpack %s", deb_file)

    def filter_relevant_packages(
        self,
        target_package: list[RepoPackage],
        package_lookup: dict[str, RepoPackage]
    ) -> list[RepoPackage]:
        relevant_packages = []
        for pkg in target_package:
            if pkg.unique_key in package_lookup:
                repo_pkg = package_lookup[pkg.unique_key]
                pkg.source_name = repo_pkg.source_name + ("-source" if repo_pkg.is_lichos_package else "")
                pkg.source_version = repo_pkg.source_version
                pkg.repository = repo_pkg.repository
                pkg.is_lichos_package = repo_pkg.is_lichos_package
                pkg.binary_name = repo_pkg.binary_name
                pkg.filename = repo_pkg.filename
                relevant_packages.append(pkg)
        return relevant_packages

    def create_docs(self, lichos_packages: list[RepoPackage], debian_packages: list[RepoPackage], output_dir: str) -> None:
        reports_dir = os.path.join(output_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        for filename, packages, title in [
            ("lichos-packages.txt", lichos_packages, "Lichos Packages"),
            ("debian-packages.txt", debian_packages, "Debian Packages"),
        ]:
            with open(os.path.join(reports_dir, filename), "w", encoding="utf-8") as f:
                f.write(f"# {title}\n")
                f.write("# Binary Package | Source Package | Version | Repository\n")
                f.write(f"# Source packages are available in this directory\n\n")
                for pkg in sorted(packages, key=lambda x: x.binary_name):
                    f.write(f"{pkg.binary_name} {pkg.source_name} {pkg.binary_version} {pkg.repository}\n")

        repositories = {pkg.repository for pkg in lichos_packages + debian_packages}
        with open(os.path.join(reports_dir, "repositories.txt"), "w", encoding="utf-8") as f:
            f.write("# Repositories Used\n")
            f.write("# These repositories were used during the build process\n\n")
            for repo in sorted(repositories):
                f.write(f"{repo}\n")
