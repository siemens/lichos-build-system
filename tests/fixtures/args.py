"""
Command argument fixtures for testing.
"""

import pytest

from tests.mocks import create_mock_args


@pytest.fixture
def mock_args():
    """Create basic mock arguments."""
    return create_mock_args()


@pytest.fixture
def mock_args_with_package():
    """Create mock args with package-specific attributes."""
    test_args = create_mock_args()
    test_args.package = "test-package"
    test_args.architecture = "arm64"
    test_args.branch = None
    test_args.pkg_group = "test-group/pkg"
    return test_args
