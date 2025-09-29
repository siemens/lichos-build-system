"""
Mock command arguments for testing.

Provides utilities for creating mock command line arguments
that can be used across different test scenarios.
"""

from unittest.mock import Mock


def create_mock_args(group_rpath="test-group/pkg", **kwargs) -> Mock:
    """
    Create mock command arguments for testing.

    Args:
        group_rpath: Default group/project path
        **kwargs: Additional argument attributes to set

    Returns:
        Mock object with command line argument attributes
    """
    args = Mock()
    args.project = kwargs.get("project", group_rpath)
    args.package = kwargs.get("package", "test-package")
    args.branch = kwargs.get("branch", "main")
    args.dry = kwargs.get("dry", False)
    args.debug = kwargs.get("debug", False)
    args.verbose = kwargs.get("verbose", False)
    args.host = kwargs.get("host", "gitlab.example.com")
    args.dump = kwargs.get("dump", False)
    args.command = kwargs.get("command", "test")

    # Set any additional attributes provided
    for key, value in kwargs.items():
        setattr(args, key, value)

    return args


class MockArgsBuilder:
    """
    Builder pattern for creating complex mock arguments.

    Provides a fluent interface for building mock arguments
    with method chaining for better readability in tests.
    """

    def __init__(self):
        self._args = {}

    def with_project(self, project: str):
        """Set project argument."""
        self._args["project"] = project
        return self

    def with_package(self, package: str):
        """Set package argument."""
        self._args["package"] = package
        return self

    def with_branch(self, branch: str):
        """Set branch argument."""
        self._args["branch"] = branch
        return self

    def with_host(self, host: str):
        """Set host argument."""
        self._args["host"] = host
        return self

    def with_flags(self, dry=False, debug=False, verbose=False, dump=False):
        """Set boolean flags."""
        self._args.update({"dry": dry, "debug": debug, "verbose": verbose, "dump": dump})
        return self

    def with_custom(self, **kwargs):
        """Set custom arguments."""
        self._args.update(kwargs)
        return self

    def build(self) -> Mock:
        """Build the mock arguments object."""
        return create_mock_args(**self._args)
