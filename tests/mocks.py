from unittest.mock import Mock

class MockGitLabProject:

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 123)
        self.name = kwargs.get("name", "test-package")
        self.ci_config_path = kwargs.get("ci_config_path", ".gitlab-ci.yml")
        self.builds_access_level = kwargs.get("builds_access_level", "enabled")
        self.default_branch = kwargs.get("default_branch", "main")
        self.namespace = kwargs.get("namespace", {"id": 456, "full_path": "test-group/pkg", "path": "pkg"})
        self.web_url = kwargs.get("web_url", f"https://gitlab.example.com/test-group/pkg/{self.name}")
        self.pipelines = Mock()
        self._saved = False

    def save(self):
        """Mock save method"""
        self._saved = True
        return self


class MockGitLabGroup:

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 456)
        self.name = kwargs.get("name", "test-group")
        self.projects = Mock()
        self._projects_list = kwargs.get("projects", [])
        self.subgroups = Mock()  # Mock subgroups attribute
        self._subgroups_list = kwargs.get("subgroups", [])  # Subgroups as a list

        self.projects.list = Mock(side_effect=self._projects_list_handler)
        self.subgroups.list = Mock(return_value=self._subgroups_list)  # Mock subgroups.list method

    def _projects_list_handler(self, include_subgroups=False, **kwargs):
        """Handle projects.list calls with include_subgroups parameter"""
        if include_subgroups:
            # Return both main group projects and subgroup projects
            all_projects = self._projects_list.copy()
            for subgroup in self._subgroups_list:
                all_projects.extend(subgroup._projects_list)
            return all_projects
        else:
            return self._projects_list

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

    def add_group(self, group_path: str, group: MockGitLabGroup):
        """Add a mock group"""
        self._groups[group_path] = group
        self.groups.get = Mock(side_effect=lambda path: self._groups.get(path))

    def add_project(self, project_id: int, project: MockGitLabProject):
        """Add a mock project"""
        self._projects[project_id] = project
        self.projects.get = Mock(side_effect=lambda pid: self._projects.get(pid))
