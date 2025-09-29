"""
Core fixtures for DI container and basic mocks.
"""

from unittest.mock import Mock

import pytest

from lichoscli.core.di import DIContainer
from lichoscli.core.services import (
    BuildInfoService,
    CacheService,
    ContainerService,
    DependencyService,
    EnvironmentService,
    PackageService,
    WorkspaceService,
)


@pytest.fixture
def mock_di_container():
    """Create a mock DI container with all core services mocked."""
    container = Mock(spec=DIContainer)

    package_service = Mock(spec=PackageService)
    dependency_service = Mock(spec=DependencyService)
    buildinfo_service = Mock(spec=BuildInfoService)
    workspace_service = Mock(spec=WorkspaceService)
    cache_service = Mock(spec=CacheService)
    container_service = Mock(spec=ContainerService)
    environment_service = Mock(spec=EnvironmentService)

    package_service.hierarchy_exists = Mock(return_value=True)
    package_service.get_projects = Mock()
    package_service.get_projects.return_value.path = "test-group/pkg"

    workspace_service.list_workspaces = Mock(return_value=[])
    workspace_service.get_workspaces_by_package = Mock(return_value=[])

    def obtain_ref_side_effect(service_type):
        if service_type == PackageService:
            return package_service
        elif service_type == DependencyService:
            return dependency_service
        elif service_type == BuildInfoService:
            return buildinfo_service
        elif service_type == WorkspaceService:
            return workspace_service
        elif service_type == CacheService:
            return cache_service
        elif service_type == ContainerService:
            return container_service
        elif service_type == EnvironmentService:
            return environment_service
        else:
            raise ValueError(f"Unknown service type: {service_type}")

    container.obtain_ref.side_effect = obtain_ref_side_effect

    container.package_service = package_service
    container.dependency_service = dependency_service
    container.buildinfo_service = buildinfo_service
    container.workspace_service = workspace_service
    container.cache_service = cache_service
    container.container_service = container_service
    container.environment_service = environment_service
    container.get_editor_strategy = Mock(return_value=Mock())

    return container
