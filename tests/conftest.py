# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""
Pytest configuration file.
Contains fixtures used across all tests.
"""

pytest_plugins = [
    "tests.fixtures.core",
    "tests.fixtures.args",
    "tests.fixtures.gitlab",
    "tests.fixtures.git",
    "tests.fixtures.mocks",
]
