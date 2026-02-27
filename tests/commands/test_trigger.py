# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import unittest
from unittest.mock import Mock

from lichoscli.commands.trigger import TriggerCommand
from lichoscli.core.services import PackageService
from lichoscli.core.models import Pipeline
from tests.mocks import create_mock_args


class TestTriggerCommand(unittest.TestCase):
    def setUp(self):
        self.di_container = Mock()
        self.package_service = Mock(spec=PackageService)
        self.di_container.obtain_ref.return_value = self.package_service

    def test_parse_variables_valid(self):
        args = create_mock_args()
        args.package = "test-package"
        args.job = None
        args.all = False
        args.variable = ["KEY1=value1", "KEY2=value2", "KEY3=value with spaces"]
        args.branch = "main"

        cmd = TriggerCommand(self.di_container, args)

        expected = {
            "KEY1": "value1",
            "KEY2": "value2",
            "KEY3": "value with spaces"
        }
        self.assertEqual(cmd.variables, expected)

    def test_parse_variables_with_equals_in_value(self):
        args = create_mock_args()
        args.package = "test-package"
        args.job = None
        args.all = False
        args.variable = ["URL=https://example.com?key=value"]
        args.branch = "main"

        cmd = TriggerCommand(self.di_container, args)

        expected = {"URL": "https://example.com?key=value"}
        self.assertEqual(cmd.variables, expected)

    def test_parse_variables_invalid_format(self):
        args = create_mock_args()
        args.package = "test-package"
        args.job = None
        args.all = False
        args.variable = ["INVALID_NO_EQUALS"]
        args.branch = "main"

        with self.assertRaises(ValueError) as context:
            TriggerCommand(self.di_container, args)

        self.assertIn("Invalid variable format", str(context.exception))
        self.assertIn("INVALID_NO_EQUALS", str(context.exception))

    def test_parse_variables_none(self):
        args = create_mock_args()
        args.package = "test-package"
        args.job = None
        args.all = False
        args.variable = None
        args.branch = "main"

        cmd = TriggerCommand(self.di_container, args)
        self.assertIsNone(cmd.variables)

    def test_trigger_single_package_with_variables(self):
        args = create_mock_args()
        args.package = "test-package"
        args.job = None
        args.all = False
        args.variable = ["ENV=production", "DEBUG=false"]
        args.branch = "main"

        mock_package = Mock()
        mock_pipeline = Mock(spec=Pipeline)
        mock_pipeline.web_url = "https://gitlab.com/test/pipeline/123"
        mock_package.pipelines.trigger_build.return_value = mock_pipeline
        self.package_service.get_package.return_value = mock_package

        cmd = TriggerCommand(self.di_container, args)
        result = cmd._trigger_single_package()

        self.assertEqual(result, 0)
        expected_vars = {"ENV": "production", "DEBUG": "false"}
        mock_package.pipelines.trigger_build.assert_called_once_with("main", expected_vars)

    def test_trigger_single_package_without_variables(self):
        args = create_mock_args()
        args.package = "test-package"
        args.job = None
        args.all = False
        args.variable = None
        args.branch = "main"

        mock_package = Mock()
        mock_pipeline = Mock(spec=Pipeline)
        mock_pipeline.web_url = "https://gitlab.com/test/pipeline/123"
        mock_package.pipelines.trigger_build.return_value = mock_pipeline
        self.package_service.get_package.return_value = mock_package

        cmd = TriggerCommand(self.di_container, args)
        result = cmd._trigger_single_package()

        self.assertEqual(result, 0)
        mock_package.pipelines.trigger_build.assert_called_once_with("main", None)

    def test_trigger_all_packages_with_variables(self):
        args = create_mock_args()
        args.package = None
        args.job = None
        args.all = True
        args.variable = ["BUILD_TYPE=release"]
        args.branch = "main"

        mock_package1 = Mock()
        mock_package1.name = "package1"
        mock_package1.ci_config_path = ".gitlab-ci.yml"
        mock_package1.has_branch.return_value = True
        mock_pipeline1 = Mock(spec=Pipeline)
        mock_pipeline1.web_url = "https://gitlab.com/test/pipeline/1"
        mock_package1.pipelines.trigger_build.return_value = mock_pipeline1

        mock_package2 = Mock()
        mock_package2.name = "package2"
        mock_package2.ci_config_path = ".gitlab-ci.yml"
        mock_package2.has_branch.return_value = True
        mock_pipeline2 = Mock(spec=Pipeline)
        mock_pipeline2.web_url = "https://gitlab.com/test/pipeline/2"
        mock_package2.pipelines.trigger_build.return_value = mock_pipeline2

        self.package_service.get_all_packages.return_value = [mock_package1, mock_package2]

        cmd = TriggerCommand(self.di_container, args)
        result = cmd._trigger_all_packages()

        self.assertEqual(result, 0)
        expected_vars = {"BUILD_TYPE": "release"}
        mock_package1.pipelines.trigger_build.assert_called_once_with("main", expected_vars)
        mock_package2.pipelines.trigger_build.assert_called_once_with("main", expected_vars)


if __name__ == "__main__":
    unittest.main()
