# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class BuildUtils:

    @staticmethod
    def normalize_architecture(arch: str) -> str:
        """Normalize architecture name using the arch map."""
        arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
        return arch_map.get(arch, arch)

    @staticmethod
    def get_package_name(package_name_arg: str):
        if not package_name_arg or package_name_arg == "." or package_name_arg == "":
            from lichoscli.core.models.git.git_repo import GitRepo
            return GitRepo(".").package_name
        return package_name_arg

    @staticmethod
    def check_local_package_exists(package_name: str) -> bool:
        """Check if a local package directory or file exists."""
        if os.path.exists(package_name):
            logger.error("Please remove the local file or directory '%s' first", package_name)
            return True
        return False

    @staticmethod
    def is_web_url(value: str) -> bool:
        """Return True if *value* looks like an http/https URL."""
        return value.startswith("http://") or value.startswith("https://")

    @staticmethod
    def get_branch_name(branch_name_arg: str) -> str:
        """
        Get branch name from argument or current git branch.
        If argument is empty, return current branch name.
        """
        if not branch_name_arg or branch_name_arg == ".":
            from lichoscli.core.models.git.git_repo import GitRepo
            return GitRepo(".").active_branch
        return branch_name_arg

    @staticmethod
    def create_tmp_env_file(env):
        env_file = tempfile.NamedTemporaryFile(prefix=".gitlab_env.", dir=".", mode="w", delete=False)
        for key in env:
            logger.debug("%s=%s", key, env[key])
            env_file.write(f"{key}={env[key]}\n")
        env_file.close()
        return env_file

    @staticmethod
    def sanitize_container_name(name: str) -> str:
        """Sanitize a string to be used as a container name.

        Docker container names must:
        - Use only [a-zA-Z0-9][a-zA-Z0-9_.-]* characters
        - Not start with a dot or dash
        - Be between 1 and 63 characters
        """
        if not name:
            return "unnamed"

        sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)

        sanitized = re.sub(r"^[.-]+", "", sanitized)

        if sanitized and not sanitized[0].isalnum():
            sanitized = "c" + sanitized

        if not sanitized:
            sanitized = "unnamed"

        if len(sanitized) > 63:
            sanitized = sanitized[:63]

        return sanitized

    @staticmethod
    def expand_var(env):
        for key, value in env.items():
            if value is None:  # skip protected variables
                continue
            env[key] = re.sub(r"\${([A-Z_][A-Z0-9_]*)}", lambda m: env.get(m.group(1), ""), value)
        return env

    @staticmethod
    def update_environment_from_file(env, tmpdir):
        try:
            with open(os.path.join(tmpdir.name, "variables.env"), encoding="utf-8") as f:
                variables = f.read()
                env |= dict(line.split("=", 1) for line in variables.splitlines() if "=" in line)
        finally:
            tmpdir.cleanup()
        return env
