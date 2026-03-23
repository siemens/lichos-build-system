# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Filesystem provider for local file-based services."""

from .notify_service import FilesystemNotifyService

__all__ = [
    "FilesystemNotifyService",
]
