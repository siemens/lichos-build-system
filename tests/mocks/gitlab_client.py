# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock

from .gitlab_project import MockGitLabProject


class MockGitLab:

    def __init__(self):
        self.groups = Mock()
        self.projects = Mock()
        self._groups = {}
        self._projects = {}
        self.projects.create = self._create_project

    def _create_project(self, data):
        """Mock create project method"""

        project = {
            "name": data.get("name"),
            "namespace_id": data.get("namespace_id"),
            "ci_config_path": data.get("ci_config_path"),
            "default_branch": data.get("default_branch"),
            "builds_access_level": data.get("builds_access_level"),
        }
        new_project = MockGitLabProject(**project)
        self._projects[new_project.id] = new_project
        return new_project

    def add_group(self, group_path: str, group):
        """Add a mock group"""
        self._groups[group_path] = group
        self.groups.get = Mock(side_effect=self._groups.get)

    def add_project(self, project_id: int, project):
        """Add a mock project"""
        self._projects[project_id] = project
        self.projects.get = Mock(side_effect=self._projects.get)
