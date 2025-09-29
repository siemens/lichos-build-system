#!/usr/bin/python3

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import requests

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)
LICHOS_VERSION_PATTERN = re.compile(r"lichos\d+")


@dataclass
class Package:
    binary_name: str
    source_name: str
    version: str
    repository: str
    is_lichos_package: bool = False

    @property
    def unique_key(self) -> str:
        return f"{self.binary_name}:{self.version}"


class CollectSourcesCommand(Command):
    """Generate GPL compliance archive with source packages"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.branch = args.branch
        self.output_dir = args.output_dir or "gpl-compliance"
        self.job_name = args.job_name

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="Package name for the image build")
        sp.add_argument("--job-name", default="build-arm64", help="Job name to get artifacts from")
        sp.add_argument("--output-dir", "-o", help="Output directory for GPL compliance archive")

    def execute(self) -> int:
        pkg = self.package_service.get_package(self.package_name)
        if not pkg:
            return 1

        artifacts_dir = None
        try:
            latest_pipeline = pkg.pipelines.get_latest(self.branch)
            if not latest_pipeline:
                logger.error("No pipeline found for branch %s", self.branch)
                return 1

            jobs = latest_pipeline.jobs.list()
            target_job = next((job for job in jobs if job.name == self.job_name), None)

            if not target_job:
                logger.error("Job %s not found in pipeline", self.job_name)
                return 1

            artifacts_dir = target_job.artifacts.download_as_directory()
            if not artifacts_dir:
                return 1

            package_lookup = self._parse_packages(artifacts_dir)
            if not package_lookup:
                return 1

            installed_packages = self._parse_installed_packages(artifacts_dir)
            if not installed_packages:
                return 1

            relevant_packages = self.filter_relevant_packages(installed_packages, package_lookup)
            self.setup_dirs()

            lichos_packages = [pkg for pkg in relevant_packages if pkg.is_lichos_package]
            debian_packages = [pkg for pkg in relevant_packages if not pkg.is_lichos_package]

            self._download_lichos_sources(lichos_packages)

            processed_buildinfo_files = set()
            lichos_packages = self._process_buildinfo_recursively(
                lichos_packages, package_lookup, processed_buildinfo_files
            )

            self._download_debian_sources(debian_packages)
            self._create_docs(lichos_packages, debian_packages)

            archive_name = f"gpl-compliance-{self.package_name}-{self.branch.replace('/', '_')}.tar.gz"
            subprocess.run(["tar", "-czf", archive_name, "-C", ".", self.output_dir], check=True)

            return 0
        finally:
            if artifacts_dir:
                shutil.rmtree(artifacts_dir.name)

    def setup_dirs(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(os.path.join(self.output_dir, "lichos-sources"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "debian-sources"), exist_ok=True)

    def _parse_packages_from_buildinfo(self, buildinfo_path: str) -> Tuple[List[Package], List[Package]]:
        with open(buildinfo_path, "r", encoding="utf-8") as f:
            content = f.read()

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

                pkg = Package(
                    pkg_name,
                    pkg_name,
                    version,
                    "unknown",
                    bool(LICHOS_VERSION_PATTERN.search(version)),
                )
                (lichos_packages if pkg.is_lichos_package else debian_packages).append(pkg)

        return lichos_packages, debian_packages

    def _find_repos_dir(self, artifacts_dir: str) -> Optional[str]:
        repos_dir = os.path.join(artifacts_dir, "repos")
        if os.path.exists(repos_dir):
            return repos_dir

        for root, dirs, _ in os.walk(artifacts_dir):
            if "repos" in dirs:
                return os.path.join(root, "repos")
        return None

    def _parse_packages(self, artifacts_dir) -> Dict[str, Package]:
        repos_dir = self._find_repos_dir(artifacts_dir.name)
        if not repos_dir:
            return {}

        package_lookup = {}
        repo_files = [f for f in os.listdir(repos_dir) if os.path.isfile(os.path.join(repos_dir, f))]

        for filename in repo_files:
            filepath = os.path.join(repos_dir, filename)
            packages = self._parse_repo_file(filepath)
            for pkg in packages:
                package_lookup[pkg.unique_key] = pkg

        return package_lookup

    def _parse_repo_file(self, filepath: str) -> List[Package]:
        packages = []
        repository_url = None

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        current_package = {}
        current_field = None

        for line in lines:
            original_line = line
            line = line.strip()

            if line.startswith("# Repository URL:"):
                repository_url = line.split(":", 1)[1].strip()
                continue

            if not line or line.startswith("#"):
                continue

            if line.startswith("Package:"):
                if current_package:
                    pkg = self._create_package_from_entry(current_package, repository_url)
                    if pkg:
                        packages.append(pkg)

                current_package = {"Package": line.split(":", 1)[1].strip()}
                current_field = "Package"

            elif ":" in line and current_package and not original_line.startswith((" ", "\t")):
                key, value = line.split(":", 1)
                current_field = key.strip()
                current_package[current_field] = value.strip()

            elif current_package and current_field and original_line.startswith((" ", "\t")):
                current_package[current_field] += " " + line

        if current_package:
            pkg = self._create_package_from_entry(current_package, repository_url)
            if pkg:
                packages.append(pkg)

        return packages

    def _create_package_from_entry(self, package_entry: Dict[str, str], repository_url: str) -> Package:
        binary_name = package_entry.get("Package", "")
        version = package_entry.get("Version", "")
        source_name = package_entry.get("Source", binary_name)
        is_lichos = bool(LICHOS_VERSION_PATTERN.search(version))
        return Package(binary_name, source_name, version, repository_url, is_lichos)

    def filter_relevant_packages(
        self, installed_packages: List[Package], package_lookup: Dict[str, Package]
    ) -> List[Package]:
        relevant_packages = []
        for installed_pkg in installed_packages:
            if installed_pkg.unique_key in package_lookup:
                repo_pkg = package_lookup[installed_pkg.unique_key]
                installed_pkg.source_name = repo_pkg.source_name + ("-source" if repo_pkg.is_lichos_package else "")
                installed_pkg.repository = repo_pkg.repository
                installed_pkg.is_lichos_package = repo_pkg.is_lichos_package
                installed_pkg.binary_name = repo_pkg.binary_name
                relevant_packages.append(installed_pkg)
        return relevant_packages

    def _download_file(self, url: str, dest_path: str) -> bool:
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

    def _download_debian_sources(self, packages: List[Package]):
        output_dir = os.path.join(self.output_dir, "debian-sources")

        for package in packages:
            base_url = f"{package.repository}/pool/main/{package.source_name[0]}/{package.source_name}"
            dsc_filename = f"{package.source_name}_{package.version}.dsc"
            dsc_url = f"{base_url}/{dsc_filename}"
            dsc_dest_path = os.path.join(output_dir, dsc_filename)

            if self._download_file(dsc_url, dsc_dest_path):
                files_to_download = self._parse_dsc_files(dsc_dest_path)

                for filename in files_to_download:
                    url = f"{base_url}/{filename}"
                    dest_path = os.path.join(output_dir, filename)

                    if not self._download_file(url, dest_path) and os.path.exists(dest_path):
                        os.remove(dest_path)

    def _parse_dsc_files(self, dsc_path: str) -> List[str]:
        files_to_download = []

        with open(dsc_path, "r", encoding="utf-8") as f:
            content = f.read()

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

    def _download_lichos_sources(self, packages: List[Package]):
        output_dir = os.path.join(self.output_dir, "lichos-sources")

        for package in packages:
            base_url = f"{package.repository}/pool/{package.source_name[0]}/{package.source_name}"
            filename = f"{package.source_name}_{package.version}_all.deb"
            url = f"{base_url}/{filename}"
            temp_file = os.path.join(output_dir, filename)

            if self._download_file(url, temp_file):
                self._unpack_lichos_source(temp_file, output_dir, package.source_name)
                os.remove(temp_file)
            elif os.path.exists(temp_file):
                os.remove(temp_file)

    def _unpack_lichos_source(self, deb_file: str, output_dir: str, source_name: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(["dpkg-deb", "-x", deb_file, temp_dir], check=True)

            source_dir = os.path.join(output_dir, source_name)
            os.makedirs(source_dir, exist_ok=True)

            for root, _, files in os.walk(temp_dir):
                for file in files:
                    src_file = os.path.join(root, file)
                    rel_path = os.path.relpath(src_file, temp_dir)
                    dest_file = os.path.join(source_dir, rel_path)

                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    shutil.copy2(src_file, dest_file)

    def _create_docs(self, lichos_packages: List[Package], debian_packages: List[Package]):
        for filename, packages, title, source_dir in [
            (
                "lichos-packages.txt",
                lichos_packages,
                "Lichos Packages",
                "lichos-sources",
            ),
            (
                "debian-packages.txt",
                debian_packages,
                "Debian Packages",
                "debian-sources",
            ),
        ]:
            with open(os.path.join(self.output_dir, filename), "w", encoding="utf-8") as f:
                f.write(f"# {title}\n")
                f.write("# Binary Package | Source Package | Version | Repository\n")
                f.write(f"# Source packages are available in {source_dir}/ directory\n\n")
                for pkg in sorted(packages, key=lambda x: x.binary_name):
                    f.write(f"{pkg.binary_name} {pkg.source_name} {pkg.version} {pkg.repository}\n")

        repositories = {pkg.repository for pkg in lichos_packages + debian_packages}
        with open(os.path.join(self.output_dir, "repositories.txt"), "w", encoding="utf-8") as f:
            f.write("# Repositories Used\n")
            f.write("# These repositories were used during the build process\n\n")
            for repo in sorted(repositories):
                f.write(f"{repo}\n")

    def _process_buildinfo_recursively(
        self,
        lichos_packages: List[Package],
        package_lookup: Dict[str, Package],
        processed_buildinfo_files: Set[str],
    ) -> List[Package]:
        lichos_src_dir = os.path.join(self.output_dir, "lichos-sources")

        new_buildinfo_files = [
            (file, os.path.join(root, file))
            for root, _, files in os.walk(lichos_src_dir)
            for file in files
            if file.endswith(".buildinfo") and file not in processed_buildinfo_files
        ]

        if not new_buildinfo_files:
            return lichos_packages

        new_lichos_packages = []
        existing_lichos_names = {pkg.source_name for pkg in lichos_packages}
        new_lichos_names = set()

        for file, buildinfo_path in new_buildinfo_files:
            processed_buildinfo_files.add(file)
            extracted_lichos_packages, _ = self._parse_packages_from_buildinfo(buildinfo_path)

            for pkg in extracted_lichos_packages:
                if pkg.source_name not in existing_lichos_names and pkg.source_name not in new_lichos_names:
                    new_lichos_packages.append(pkg)
                    new_lichos_names.add(pkg.source_name)

        if new_lichos_packages:
            filtered_new_packages = self.filter_relevant_packages(new_lichos_packages, package_lookup)
            self._download_lichos_sources(filtered_new_packages)

        lichos_packages.extend(new_lichos_packages)

        return self._process_buildinfo_recursively(lichos_packages, package_lookup, processed_buildinfo_files)

    def _find_installed_packages_file(self, artifacts_dir: str) -> Optional[str]:
        packages_file = os.path.join(artifacts_dir, "installed-packages")
        if os.path.exists(packages_file):
            return packages_file

        for root, _, files in os.walk(artifacts_dir):
            if "installed-packages" in files:
                return os.path.join(root, "installed-packages")
        return None

    def _parse_installed_packages(self, artifacts_dir) -> List[Package]:
        packages_file = self._find_installed_packages_file(artifacts_dir.name)
        if not packages_file:
            return []

        installed_packages = []

        with open(packages_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    installed_packages.append(
                        Package(
                            binary_name=parts[0],
                            source_name=parts[0],
                            version=parts[1],
                            repository="unknown",
                            is_lichos_package=False,
                        )
                    )

        return installed_packages
