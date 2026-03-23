# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import unittest
from unittest.mock import Mock

import pytest

from lichoscli.commands.abortbuild import AbortbuildCommand
from lichoscli.core.models import Pipeline
from lichoscli.core.models.pipeline_status import PipelineStatus
from lichoscli.core.services import PackageService, WorkspaceService
from lichoscli.ui import UserInterface
from tests.mocks import create_mock_args


class TestAbortbuildCommand(unittest.TestCase):
    def setUp(self):
        self.di_container = Mock()
        self.package_service = Mock(spec=PackageService)
        self.workspace_service = Mock(spec=WorkspaceService)

        mock_ui = Mock(spec=UserInterface)
        mock_ui.output = Mock()
        mock_ui.output.console = Mock()
        mock_ui.prompts = Mock()

        def obtain_ref_side_effect(service_type):
            if service_type is UserInterface:
                return mock_ui
            if service_type is PackageService:
                return self.package_service
            if service_type is WorkspaceService:
                return self.workspace_service
            raise ValueError(f"Unknown service type: {service_type}")

        self.di_container.obtain_ref.side_effect = obtain_ref_side_effect
        self.mock_ui = mock_ui

    def _make_args(self, package=None, branch="main"):
        args = create_mock_args()
        args.package = package
        args.branch = branch
        return args

    def _make_pipeline(self, pipeline_id, status, ref="main"):
        pipeline = Mock(spec=Pipeline)
        pipeline.id = pipeline_id
        pipeline.status = status
        pipeline.ref = ref
        pipeline.cancel = Mock(return_value=True)
        return pipeline

    # Test 1: no package, no workspace → error
    def test_no_package_no_workspace_returns_error(self):
        self.workspace_service.get_current_workspace.return_value = None
        args = self._make_args(package=None)
        cmd = AbortbuildCommand(self.di_container, args)

        result = cmd.execute()

        self.assertEqual(result, 1)
        self.workspace_service.get_current_workspace.assert_called_once()

    # Test 2: no package, workspace present → only packages with active pipelines shown → select_many → cancel
    def test_no_package_workspace_select_many_then_cancel(self):
        mock_pkg_active = Mock()
        mock_pkg_active.name = "u-boot"
        mock_pkg_idle = Mock()
        mock_pkg_idle.name = "idle-pkg"
        mock_workspace = Mock()
        mock_workspace.packages = [mock_pkg_active, mock_pkg_idle]
        self.workspace_service.get_current_workspace.return_value = mock_workspace

        pipeline = self._make_pipeline(42, PipelineStatus.RUNNING)
        mock_package_active = Mock()
        mock_package_active.pipelines.list.return_value = [pipeline]
        mock_package_idle = Mock()
        mock_package_idle.pipelines.list.return_value = [self._make_pipeline(10, PipelineStatus.SUCCESS)]

        def get_package_side_effect(name):
            return mock_package_active if name == "u-boot" else mock_package_idle

        self.package_service.get_package.side_effect = get_package_side_effect
        self.mock_ui.prompts.select_many.return_value = ["u-boot"]

        args = self._make_args(package=None)
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        # Only u-boot should appear in choices (idle-pkg has no active pipelines)
        call_args = self.mock_ui.prompts.select_many.call_args
        choice_values = [c.value for c in call_args[0][2]]
        self.assertIn("u-boot", choice_values)
        self.assertNotIn("idle-pkg", choice_values)
        pipeline.cancel.assert_called_once()

    # Test 3: no package, workspace → all packages have no active pipelines → returns 0 without prompt
    def test_no_package_workspace_no_active_pipelines_skips_prompt(self):
        mock_pkg = Mock()
        mock_pkg.name = "idle-pkg"
        mock_workspace = Mock()
        mock_workspace.packages = [mock_pkg]
        self.workspace_service.get_current_workspace.return_value = mock_workspace

        mock_package = Mock()
        mock_package.pipelines.list.return_value = [self._make_pipeline(1, PipelineStatus.SUCCESS)]
        self.package_service.get_package.return_value = mock_package

        args = self._make_args(package=None)
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        self.mock_ui.prompts.select_many.assert_not_called()

    # Test 3b: no package, workspace → select_many returns None (cancelled)
    def test_no_package_workspace_select_cancel_returns_0(self):
        mock_pkg = Mock()
        mock_pkg.name = "u-boot"
        mock_workspace = Mock()
        mock_workspace.packages = [mock_pkg]
        self.workspace_service.get_current_workspace.return_value = mock_workspace

        pipeline = self._make_pipeline(42, PipelineStatus.RUNNING)
        mock_package = Mock()
        mock_package.pipelines.list.return_value = [pipeline]
        self.package_service.get_package.return_value = mock_package
        self.mock_ui.prompts.select_many.return_value = None

        args = self._make_args(package=None)
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        pipeline.cancel.assert_not_called()

    # Test 4: no active pipelines → returns 0 with info message
    def test_no_active_pipelines_returns_0(self):
        final_pipeline = self._make_pipeline(10, PipelineStatus.SUCCESS)
        mock_package = Mock()
        mock_package.pipelines.list.return_value = [final_pipeline]
        self.package_service.get_package.return_value = mock_package

        args = self._make_args(package="u-boot")
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        final_pipeline.cancel.assert_not_called()
        self.mock_ui.output.print.assert_called_once()

    # Test 5: single non-final pipeline → cancel without prompt
    def test_single_pipeline_cancelled_directly(self):
        pipeline = self._make_pipeline(99, PipelineStatus.RUNNING)
        mock_package = Mock()
        mock_package.pipelines.list.return_value = [pipeline]
        self.package_service.get_package.return_value = mock_package

        args = self._make_args(package="u-boot")
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        pipeline.cancel.assert_called_once()
        self.mock_ui.prompts.select_many.assert_not_called()

    # Test 6: multiple non-final pipelines → select_many → cancel selected
    def test_multiple_pipelines_select_many(self):
        p1 = self._make_pipeline(1, PipelineStatus.RUNNING)
        p2 = self._make_pipeline(2, PipelineStatus.PENDING)
        p3 = self._make_pipeline(3, PipelineStatus.CREATED)
        mock_package = Mock()
        mock_package.pipelines.list.return_value = [p1, p2, p3]
        self.package_service.get_package.return_value = mock_package

        # User selects pipelines 1 and 3
        self.mock_ui.prompts.select_many.return_value = ["1", "3"]

        args = self._make_args(package="u-boot")
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        self.mock_ui.prompts.select_many.assert_called_once()
        p1.cancel.assert_called_once()
        p2.cancel.assert_not_called()
        p3.cancel.assert_called_once()

    # Test 7: package not found → returns error
    def test_package_not_found_returns_error(self):
        self.package_service.get_package.return_value = None

        args = self._make_args(package="nonexistent")
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 1)

    # Test 8: select_many returns None (cancelled) → returns 0
    def test_multiple_pipelines_select_many_cancelled(self):
        p1 = self._make_pipeline(1, PipelineStatus.RUNNING)
        p2 = self._make_pipeline(2, PipelineStatus.PENDING)
        mock_package = Mock()
        mock_package.pipelines.list.return_value = [p1, p2]
        self.package_service.get_package.return_value = mock_package

        self.mock_ui.prompts.select_many.return_value = None

        args = self._make_args(package="u-boot")
        cmd = AbortbuildCommand(self.di_container, args)
        result = cmd.execute()

        self.assertEqual(result, 0)
        p1.cancel.assert_not_called()
        p2.cancel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
