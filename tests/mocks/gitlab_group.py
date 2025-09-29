from unittest.mock import Mock


class MockGitLabGroup:

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 456)
        self.name = kwargs.get("name", "test-group")
        self.projects = Mock()
        self._projects_list = kwargs.get("projects", [])
        self.subgroups = Mock()
        self._subgroups_list = kwargs.get("subgroups", [])

        self.projects.list = Mock(side_effect=self._projects_list_handler)
        self.subgroups.list = Mock(return_value=self._subgroups_list)

    def _projects_list_handler(self, include_subgroups=False, **_kwargs):
        """Handle projects.list calls with include_subgroups parameter"""
        if include_subgroups:
            all_projects = self._projects_list.copy()
            for subgroup in self._subgroups_list:
                all_projects.extend(subgroup._projects_list)
            return all_projects
        else:
            return self._projects_list
