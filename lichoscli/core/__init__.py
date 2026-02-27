# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

# Core abstractions and interfaces for git provider support

from .config import ConfigBuilder, LichosConfig, ProviderType
from .container_factory import DIContainerFactory
from .exceptions import (
    ArtifactError,
    BranchError,
    ConfigurationError,
    GroupError,
    JobError,
    LichosCliError,
    MergeRequestError,
    PipelineError,
    ProjectFetchingError,
    ProviderError,
    ServiceError,
    TagError,
    ValidationError,
    VariableError,
)
from .models import (
    BuildDependency,
    BuildInfo,
    Job,
    MergeRequest,
    Pipeline,
    Project,
    Projects,
    Tag,
    Variable,
)
from .services import DependencyService, PackageService

__all__ = [
    # Configuration
    "LichosConfig",
    "ConfigBuilder",
    "ProviderType",
    "DIContainerFactory",
    # Models
    "BuildDependency",
    "BuildInfo",
    "Project",
    "Projects",
    "MergeRequest",
    "Pipeline",
    "Job",
    "Variable",
    "Tag",
    # Services
    "PackageService",
    "DependencyService",
    # Exceptions
    "LichosCliError",
    "ProjectFetchingError",
    "PipelineError",
    "JobError",
    "VariableError",
    "TagError",
    "MergeRequestError",
    "ArtifactError",
    "BranchError",
    "GroupError",
    "ServiceError",
    "ProviderError",
    "ValidationError",
    "ConfigurationError",
]
