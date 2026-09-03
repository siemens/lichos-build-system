# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from lichoscli.providers.gitlab.models.pipelines import GitLabPipelines


def test_trigger_build_uses_mr_pipeline_when_no_variables():
    gitlab_project = Mock()
    gitlab_project.default_branch = "main"

    core_project = Mock()
    mr = Mock()
    mr.create_pipeline.return_value = 42
    core_project.merge_requests.list.return_value = [mr]

    pipelines = GitLabPipelines(gitlab_project, core_project)
    pipelines.trigger_build("feature-branch")

    mr.create_pipeline.assert_called_once()
    gitlab_project.pipelines.create.assert_not_called()


def test_trigger_build_falls_back_to_branch_pipeline_when_variables_given():
    gitlab_project = Mock()
    gitlab_project.default_branch = "main"

    core_project = Mock()
    mr = Mock()
    core_project.merge_requests.list.return_value = [mr]

    pipelines = GitLabPipelines(gitlab_project, core_project)
    pipelines.trigger_build("feature-branch", {"KEY": "value"})

    mr.create_pipeline.assert_not_called()
    core_project.merge_requests.list.assert_not_called()
    gitlab_project.pipelines.create.assert_called_once_with(
        {"ref": "feature-branch", "variables": [{"key": "KEY", "value": "value"}]}
    )
