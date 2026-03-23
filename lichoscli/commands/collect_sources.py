#!/usr/bin/python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG
import logging
import os
import shutil
from typing import Optional

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models.repo_package import RepoPackage
from lichoscli.core.services import PackageService, RepoParserService, SourceCollectionService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class CollectSourcesCommand(Command):
    """Download source packages for GPL compliance."""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.repo_parser = di_container.obtain_ref(RepoParserService)
        self.source_collection_service = di_container.obtain_ref(SourceCollectionService)
        self.package_name = BuildUtils.get_package_name(args.package)
        self.branch = args.branch
        self.output_dir = args.output_dir or "source-packages"
        self.job_name = args.job_name

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="Package name for the image build")
        sp.add_argument("--job-name", default="build-arm64", help="Job name to get artifacts from")
        sp.add_argument("--output-dir", "-o", help="Output directory for GPL compliance archive")

    def execute(self) -> int:
        pkg = self.package_service.get_package(self.package_name)
        if not pkg:
            logger.error("Package '%s' not found", self.package_name)
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
                logger.error("No pipeline was found")
                return 1

            repos = self._parse_packages(artifacts_dir)
            if not repos:
                logger.error("No repository packages found in artifacts")
                return 1

            target_packages = self._parse_target_packages(artifacts_dir)
            if not target_packages:
                logger.error("No installed packages found in artifacts")
                return 1

            relevant_packages = self.source_collection_service.filter_relevant_packages(target_packages, repos)

            os.makedirs(self.output_dir, exist_ok=True)
            os.makedirs(os.path.join(self.output_dir, "reports"), exist_ok=True)

            lichos_packages = [pkg for pkg in relevant_packages if pkg.is_lichos_package]
            debian_packages = [pkg for pkg in relevant_packages if not pkg.is_lichos_package]

            self.source_collection_service.download_lichos_sources(lichos_packages, self.output_dir)

            processed_buildinfo_files = set()
            lichos_packages = self._process_buildinfo_recursively(
                lichos_packages, repos, processed_buildinfo_files, self.output_dir
            )

            self.source_collection_service.download_debian_sources(debian_packages, self.output_dir)
            self.source_collection_service.create_docs(lichos_packages, debian_packages, self.output_dir)

            target_packages_file = self._find_target_packages_file(artifacts_dir.name)
            if target_packages_file:
                shutil.copy(target_packages_file, os.path.join(self.output_dir, "target-packages"))
                shutil.copy(target_packages_file, os.path.join(self.output_dir, "reports", "target-packages"))
                pkg_list_path = os.path.join(self.output_dir, "target-packages")
                self.output.success(f"✓ Copied package list for capywfa: {pkg_list_path}")

            return 0
        finally:
            if artifacts_dir:
                shutil.rmtree(artifacts_dir.name)

    def _process_buildinfo_recursively(
        self,
        lichos_packages: list[RepoPackage],
        package_lookup: dict[str, RepoPackage],
        processed_buildinfo_files: set[str],
        output_dir: str,
    ) -> list[RepoPackage]:
        new_buildinfo_files = [
            (file, os.path.join(root, file))
            for root, _, files in os.walk(output_dir)
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
            extracted_lichos_packages, _ = self.repo_parser.parse_packages_from_buildinfo(buildinfo_path)

            for pkg in extracted_lichos_packages:
                if pkg.source_name not in existing_lichos_names and pkg.source_name not in new_lichos_names:
                    new_lichos_packages.append(pkg)
                    new_lichos_names.add(pkg.source_name)

        if new_lichos_packages:
            filtered_new_packages = self.source_collection_service.filter_relevant_packages(new_lichos_packages, package_lookup)
            self.source_collection_service.download_lichos_sources(filtered_new_packages, output_dir)

        lichos_packages.extend(new_lichos_packages)

        return self._process_buildinfo_recursively(lichos_packages, package_lookup, processed_buildinfo_files, output_dir)

    def _find_repos_dir(self, artifacts_dir: str) -> Optional[str]:
        repos_dir = os.path.join(artifacts_dir, "repos")
        if os.path.exists(repos_dir):
            return repos_dir

        for root, dirs, _ in os.walk(artifacts_dir):
            if "repos" in dirs:
                return os.path.join(root, "repos")
        return None

    def _parse_packages(self, artifacts_dir) -> dict[str, RepoPackage]:
        repos_dir = self._find_repos_dir(artifacts_dir.name)
        if not repos_dir:
            return {}
        return self.repo_parser.parse_packages_from_dir(repos_dir)
    
    def _find_target_packages_file(self, artifacts_dir: str) -> Optional[str]:
        packages_file = os.path.join(artifacts_dir, "target-packages")
        if os.path.exists(packages_file):
            return packages_file

        for root, _, files in os.walk(artifacts_dir):
            if "target-packages" in files:
                return os.path.join(root, "target-packages")
        return None

    def _parse_target_packages(self, artifacts_dir) -> list[RepoPackage]:
        packages_file = self._find_target_packages_file(artifacts_dir.name)
        if not packages_file:
            return []
        return self.repo_parser.parse_target_packages_file(packages_file)