# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService, WorkspaceService
from lichoscli.ui.models import Choice
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class AbortbuildCommand(Command):
    """Cancel non-final pipelines for a workspace package"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package) if args.package else None
        self.branch = args.branch
        self.package_service = di_container.obtain_ref(PackageService)
        self.workspace_service = di_container.obtain_ref(WorkspaceService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="package name to abort build for")

    def execute(self):
        selected_names = [self.package_name] if self.package_name else None

        if not selected_names:
            workspace = self.workspace_service.get_current_workspace()
            if not workspace:
                logger.error("No active workspace found. Please specify a package name or enter a workspace.")
                return 1

            # Pre-fetch active pipelines; only packages with active pipelines are selectable
            active_pipelines_by_name: dict[str, list] = {}
            for wp in workspace.packages:
                package = self.package_service.get_package(wp.name)
                if package is None:
                    continue
                pipelines = [p for p in package.pipelines.list(self.branch, per_page=20) if not p.status.is_final]
                if pipelines:
                    active_pipelines_by_name[wp.name] = pipelines

            if not active_pipelines_by_name:
                self.output.print("No active pipelines found in the current workspace.")
                return 0

            choices = [Choice(value=name, label=name) for name in active_pipelines_by_name]
            selected_names = self.prompts.select_many(
                "Select packages",
                "Choose packages to abort build for",
                choices,
            )
            if not selected_names:
                return 0

            failed_count = 0
            for name in selected_names:
                result = self._abort_active_pipelines(name, active_pipelines_by_name[name])
                if result:
                    failed_count += result
            return failed_count

        # Explicit package(s) provided — fetch pipelines on demand
        failed_count = 0
        for package_name in selected_names:
            result = self._abort_package(package_name)
            if result:
                failed_count += result
        return failed_count

    def _abort_package(self, package_name: str) -> int:
        package = self.package_service.get_package(package_name)
        if package is None:
            logger.error("Package '%s' not found", package_name)
            return 1

        active_pipelines = [p for p in package.pipelines.list(self.branch, per_page=20) if not p.status.is_final]
        return self._abort_active_pipelines(package_name, active_pipelines)

    def _abort_active_pipelines(self, package_name: str, active_pipelines: list) -> int:
        if not active_pipelines:
            self.output.print(f"No active pipelines found for {package_name}")
            return 0

        if len(active_pipelines) == 1:
            return self._cancel_pipelines(active_pipelines)

        choices = [
            Choice(
                value=str(p.id),
                label=f"#{p.id} [{p.status.value}] ref:{p.ref}",
            )
            for p in active_pipelines
        ]
        selected_ids = self.prompts.select_many(
            "Select pipelines",
            "Choose pipelines to cancel",
            choices,
        )
        if not selected_ids:
            return 0

        id_set = set(selected_ids)
        pipelines_to_cancel = [p for p in active_pipelines if str(p.id) in id_set]
        return self._cancel_pipelines(pipelines_to_cancel)

    def _cancel_pipelines(self, pipelines):
        failed_count = 0
        for pipeline in pipelines:
            success = pipeline.cancel()
            if success:
                self.output.success(
                    f"✓ Cancelled pipeline #{pipeline.id} [{pipeline.status.value}] ref:{pipeline.ref}",
                )
            else:
                logger.error("Failed to cancel pipeline #%s", pipeline.id)
                failed_count += 1
        return failed_count
