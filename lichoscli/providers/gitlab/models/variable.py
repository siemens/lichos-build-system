"""GitLab Variable model wrapper."""

from typing import Optional

from gitlab.v4.objects import Variable as GitLabVariableModel

from lichoscli.core.models import Variable


class GitLabVariable(Variable):
    """Wrapper for GitLab Variable objects."""

    def __init__(self, gitlab_variable: GitLabVariableModel, inherited: bool = False):
        self._variable = gitlab_variable
        self._inherited = inherited

    @property
    def key(self) -> str:
        return self._variable.key

    @property
    def value(self) -> str:
        return self._variable.value

    @property
    def variable_type(self) -> str:
        return getattr(self._variable, "variable_type", "env_var")

    @property
    def protected(self) -> bool:
        return getattr(self._variable, "protected", False)

    @property
    def masked(self) -> bool:
        return getattr(self._variable, "masked", False)

    @property
    def environment_scope(self) -> Optional[str]:
        return getattr(self._variable, "environment_scope", None)

    @property
    def raw(self) -> bool:
        return getattr(self._variable, "raw", False)

    @property
    def description(self) -> Optional[str]:
        return getattr(self._variable, "description", None)

    @property
    def inherited(self) -> bool:
        return self._inherited

    def save(self):
        """Save changes to the variable."""
        return self._variable.save()

    def delete(self):
        """Delete the variable."""
        return self._variable.delete()
