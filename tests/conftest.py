"""
Pytest configuration file.
Contains fixtures used across all tests.
"""

from tests.fixtures import mock_git_repo

# The mock_git_repo fixture will automatically be used for all tests
# It's imported here to ensure that it's available for pytest discovery
