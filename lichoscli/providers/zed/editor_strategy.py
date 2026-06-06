# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import json
import logging
import os
import socket
import subprocess
import time
from typing import Optional

from lichoscli.core.services.editor import (
    EditorConfig,
    EditorLaunchResult,
    EditorStrategy,
)
from lichoscli.core.services.environment import BuildEnvironment
from lichoscli.ui.interfaces import OutputWriter
from lichoscli.utils.constants import LICHOS_MARKER

logger = logging.getLogger(__name__)

_DEVCONTAINER_DIR = ".devcontainer"
_DEVCONTAINER_JSON = "devcontainer.json"



class ZedEditorStrategy(EditorStrategy):
    """Zed implementation of EditorStrategy using dev container definitions.

    Instead of SSH (like the VS Code strategy), Zed connects to a container
    through a ``.devcontainer/devcontainer.json`` that is generated
    dynamically from the build environment pulled from the CI pipeline.
    When Zed opens the project directory it detects the devcontainer
    definition and builds/starts the container automatically.

    The ``onCreateCommand`` runs ``lichos-gbp-install`` so that the
    repository setup (apt sources, build dependencies) is available
    inside the container.
    """

    def __init__(self, output: OutputWriter):
        """Initialize the Zed editor strategy."""
        self.output = output
        self.console = output.console

    def get_editor_name(self) -> str:
        """Get the name of this editor strategy."""
        return "zed"

    def setup_remote_connection(self, config: EditorConfig) -> bool:
        """Generate the .devcontainer/devcontainer.json from the build environment.

        The build environment (image, env vars, REPO_SETUP_CMD) is carried on
        the *config* object and written out so that Zed can discover it.
        """
        if not config.container_name:
            logger.error("Container name is required for Zed dev container setup")
            return False

        build_env = getattr(config, "build_environment", None)
        if not build_env:
            logger.error("Build environment is required to generate devcontainer.json")
            return False

        return self._write_devcontainer(build_env, config.project_path, config.container_name, config.network)

    def launch_editor(self, config: EditorConfig) -> EditorLaunchResult:
        """Launch Zed on the project directory.

        Zed auto-detects ``.devcontainer/devcontainer.json`` and offers to
        reopen the project inside the container.
        """
        try:
            project_dir = os.getcwd()
            zed_cmd = ["zed", "--dev-container", project_dir]

            logger.info("Launching Zed with command: %s", " ".join(zed_cmd))

            time.sleep(1)

            process = subprocess.Popen(
                zed_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

            self.console.print("✓ Zed launched — it should detect the .devcontainer and offer to reopen in container")
            self.console.print(f"Project directory: {project_dir}")
            self.console.print(f"Zed process started with PID: {process.pid}")

            return EditorLaunchResult(success=True, process_id=process.pid)

        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            error_msg = f"Failed to launch Zed automatically: {e}"
            logger.warning(error_msg)

            self.console.print("✗ Zed launch failed. Open the project manually:")
            self.console.print(f"  zed {os.getcwd()}")

            return EditorLaunchResult(success=False, error_message=error_msg)

    def wait_for_connection_ready(self, config: EditorConfig, timeout_seconds: int = 60) -> bool:
        """Not applicable — Zed manages the container lifecycle itself."""
        return True

    def cleanup_connection(self, config: EditorConfig) -> None:
        """Remove the generated .devcontainer/devcontainer.json only if we own it."""
        json_path = os.path.join(os.getcwd(), _DEVCONTAINER_DIR, _DEVCONTAINER_JSON)
        try:
            if os.path.exists(json_path):
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("name", "").startswith(LICHOS_MARKER):
                    os.unlink(json_path)
                    devcontainer_path = os.path.join(os.getcwd(), _DEVCONTAINER_DIR)
                    if os.path.isdir(devcontainer_path) and not os.listdir(devcontainer_path):
                        os.rmdir(devcontainer_path)
                    logger.debug("Cleaned up lichoscli-managed .devcontainer")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to clean up .devcontainer: %s", e)

    def find_free_port(self) -> int:
        """Not used by Zed but required by the abstract interface."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_lichoscli_devcontainer(json_path: str) -> bool:
        """Check whether an existing devcontainer.json was created by lichoscli."""
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("name", "").startswith(LICHOS_MARKER)
        except (OSError, json.JSONDecodeError):
            return False

    def _write_devcontainer(self, build_env: BuildEnvironment, project_path: str, container_name: str, network: Optional[str] = None) -> bool:
        """Write ``.devcontainer/devcontainer.json`` derived from *build_env*.

        If an existing devcontainer.json is present but was *not* created by
        lichoscli, refuse to overwrite it.  Our own files are always
        overwritten fresh.
        """
        devcontainer_path = os.path.join(os.getcwd(), _DEVCONTAINER_DIR)
        json_path = os.path.join(devcontainer_path, _DEVCONTAINER_JSON)

        if os.path.exists(json_path) and not self._is_lichoscli_devcontainer(json_path):
            logger.error(
                "Refusing to overwrite existing %s not managed by lichoscli",
                json_path,
            )
            self.console.print(
                f"✗ {json_path} already exists and is not managed by lichoscli — refusing to overwrite"
            )
            return False

        os.makedirs(devcontainer_path, exist_ok=True)

        container_env: dict[str, str] = {"LOCAL_UID": "${localEnv:UID}"}
        skip_keys = {"IMAGE"}
        for key, value in build_env.variables.items():
            if key not in skip_keys and value is not None:
                container_env[key] = value

        devcontainer = {
            "name": container_name,
            "image": build_env.image,
            "workspaceMount": f"source={os.getcwd()},target={project_path},type=bind",
            "workspaceFolder": project_path,
            "remoteEnv": container_env,
            "updateRemoteUserUID": False,
            "onCreateCommand": "lichos-prepare-dev-container",
        }

        run_args = ["--user=developer"]
        run_args.append(f"--name={container_name}")
        if network:
            run_args.append(f"--network={network}")
        devcontainer["runArgs"] = run_args

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(devcontainer, f, indent=2)
                f.write("\n")
            logger.info("Wrote %s", json_path)
            self.console.print(f"✓ Generated {json_path}")
            return True
        except OSError as e:
            logger.error("Failed to write devcontainer.json: %s", e)
            return False
