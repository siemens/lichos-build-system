# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock


class MockGitLabProject:

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 123)
        self.name = kwargs.get("name", "test-package")
        self.path = kwargs.get("path", self.name)
        self.archived = kwargs.get("archived", False)
        self.ci_config_path = kwargs.get("ci_config_path", ".gitlab-ci.yml")
        self.builds_access_level = kwargs.get("builds_access_level", "enabled")
        self.default_branch = kwargs.get("default_branch", "main")
        self.namespace = kwargs.get("namespace", {"id": 456, "full_path": "test-group/pkg", "path": "pkg"})
        self.web_url = kwargs.get("web_url", f"https://gitlab.example.com/test-group/pkg/{self.name}")
        self.path_with_namespace = kwargs.get(
            "path_with_namespace", f"{self.namespace.get('full_path', 'test-group/pkg')}/{self.name}"
        )
        self.pipelines = Mock()
        self.jobs = Mock()
        self.web_url = kwargs.get("web_url", f"https://gitlab.example.com/test-group/pkg/{self.name}")
        self._saved = False
        self.is_fork = kwargs.get("is_fork", False)
        self.create_fork_relation = Mock()
        self.delete_fork_relation = Mock()
        self.set_force_push = Mock(return_value=True)
        self.delete = Mock(return_value=True)
        self.delete_permanently = Mock(return_value=True)
        self.is_marked_for_deletion = kwargs.get("is_marked_for_deletion", False)

    @property
    def attributes(self):
        """python-gitlab exposes record data here; build_project rebuilds objects from it."""
        return {
            key: value for key, value in self.__dict__.items()
            if not key.startswith("_") and not isinstance(value, Mock)
        }

    def save(self):
        """Mock save method"""
        self._saved = True
        return self
