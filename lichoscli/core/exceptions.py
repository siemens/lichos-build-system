# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Core exceptions for lichoscli."""


class LichosCliError(Exception):
    """Base exception for all lichoscli errors."""


class ProjectFetchingError(LichosCliError):
    """Exception raised for project-related errors."""


class PipelineError(LichosCliError):
    """Exception raised for pipeline-related errors."""


class JobError(LichosCliError):
    """Exception raised for job-related errors."""


class VariableError(LichosCliError):
    """Exception raised for variable-related errors."""


class TagError(LichosCliError):
    """Exception raised for tag-related errors."""


class MergeRequestError(LichosCliError):
    """Exception raised for merge request-related errors."""


class ArtifactError(LichosCliError):
    """Exception raised for artifact-related errors."""


class BranchError(LichosCliError):
    """Exception raised for branch-related errors."""


class GroupError(LichosCliError):
    """Exception raised for group-related errors."""


class ServiceError(LichosCliError):
    """Exception raised for service-related errors."""


class ProviderError(LichosCliError):
    """Exception raised for provider-specific errors."""


class ValidationError(LichosCliError):
    """Exception raised for validation errors."""


class ConfigurationError(LichosCliError):
    """Exception raised for configuration errors."""
