# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import os
import socket
import subprocess
import time
from typing import Optional

from rich.console import Console
from rich.status import Status

from lichoscli.core.services import EditorConfig, EditorLaunchResult, EditorStrategy

logger = logging.getLogger(__name__)


class VSCodeEditorStrategy(EditorStrategy):
    """VS Code implementation of EditorStrategy."""

    def __init__(self):
        """Initialize the VS Code editor strategy."""
        self.console = Console()

    def get_editor_name(self) -> str:
        """Get the name of this editor strategy."""
        return "code"

    def setup_remote_connection(self, config: EditorConfig) -> bool:
        """Setup SSH configuration for VS Code remote connection."""
        try:
            if not config.ssh_port:
                logger.error("SSH port is required for VS Code remote connection")
                return False

            ssh_config_path = self._setup_ssh_config(config.ssh_port, config.container_name)
            if not ssh_config_path:
                return False

            config.ssh_config_path = ssh_config_path
            return True

        except OSError as e:
            logger.error("Failed to setup VS Code remote connection: %s", e)
            return False

    def launch_editor(self, config: EditorConfig) -> EditorLaunchResult:
        """Launch VS Code with remote SSH connection."""
        try:
            if not config.container_name:
                return EditorLaunchResult(success=False, error_message="Container name is required for VS Code launch")

            if not self.wait_for_connection_ready(config):
                logger.warning("SSH setup may not be complete, but attempting VS Code launch...")

            logger.info("Launching VS Code...")
            vscode_cmd = ["code", "--remote", f"ssh-remote+{config.container_name}", config.project_path]

            logger.info("Launching VS Code with command: %s", " ".join(vscode_cmd))

            time.sleep(1)

            process = subprocess.Popen(
                vscode_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

            self.console.print("[green]✓[/green] VS Code launched with remote SSH connection to container")
            self.console.print(f"SSH config updated: [cyan]{config.ssh_config_path}[/cyan]")
            self.console.print(f"Remote path: [cyan]{config.project_path}[/cyan]")
            self.console.print(f"VS Code process started with PID: [yellow]{process.pid}[/yellow]")

            return EditorLaunchResult(success=True, process_id=process.pid)

        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            error_msg = f"Failed to launch VS Code automatically: {e}"
            logger.warning(error_msg)

            self.console.print("[red]✗[/red] VS Code launch failed. You can manually connect using:")
            self.console.print(f"  [cyan]code --remote ssh-remote+{config.container_name} {config.project_path}[/cyan]")
            self.console.print(f"Or use SSH directly: [cyan]ssh {config.container_name}[/cyan]")
            if config.ssh_port:
                self.console.print(f"Or with explicit port: [cyan]ssh root@localhost -p {config.ssh_port}[/cyan]")

            return EditorLaunchResult(success=False, error_message=error_msg)

    def wait_for_connection_ready(self, config: EditorConfig, timeout_seconds: int = 180) -> bool:
        """Wait for SSH connection to be ready."""
        if not config.container_name:
            logger.error("Container name is required to wait for connection")
            return False

        with Status("[bold blue]Waiting for container setup to complete...", console=self.console) as status:
            status.update("[bold blue]This may take a few minutes while installing packages and configuring SSH...")

            start_time = time.time()
            setup_completed = False

            while time.time() - start_time < timeout_seconds:
                logs_cmd = ["docker", "logs", "--tail", "50", config.container_name]
                logs_result = subprocess.run(logs_cmd, capture_output=True, text=True, check=False)

                if logs_result.returncode == 0:
                    logs_output = logs_result.stdout + logs_result.stderr

                    if "Container ready for VS Code Remote - SSH connection" in logs_output:
                        status.update("[green]✓ Container setup completed!")
                        setup_completed = True
                        break

                    if "Installing openssh-server..." in logs_output:
                        status.update("[blue]Installing SSH server packages...")
                    elif "Creating developer user..." in logs_output:
                        status.update("[blue]Setting up developer user...")
                    elif "Configuring SSH daemon..." in logs_output:
                        status.update("[blue]Configuring SSH daemon...")
                    elif "Starting SSH daemon..." in logs_output:
                        status.update("[blue]Starting SSH daemon...")
                    elif "SSH daemon started successfully" in logs_output:
                        status.update("[blue]SSH daemon started successfully...")

                time.sleep(3)

        if not setup_completed:
            self.console.print("[yellow]⚠[/yellow] Setup timeout reached, but continuing to test SSH connection...")

        with Status("[bold blue]Testing SSH connection...", console=self.console) as status:
            ssh_ready_start = time.time()

            while time.time() - ssh_ready_start < 60:
                test_cmd = [
                    "ssh",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "LogLevel=ERROR",
                    config.container_name,
                    "echo",
                    "ready",
                ]

                test_result = subprocess.run(test_cmd, capture_output=True, text=True, check=False)

                if test_result.returncode == 0:
                    status.update("[green]✓ SSH connection successful!")
                    break

                elapsed = int(time.time() - ssh_ready_start)
                status.update(f"[blue]SSH connection attempt {elapsed//5 + 1} (waiting...)")
                time.sleep(1)
            else:
                self.console.print("[red]✗[/red] SSH connection failed after timeout")
                return False

        self.console.print("[green]✓[/green] SSH connection successful!")
        return True

    def cleanup_connection(self, config: EditorConfig) -> None:
        """Clean up SSH configuration."""
        logger.debug("SSH config cleanup not implemented - config persists for manual use")

    def find_free_port(self) -> int:
        """Find a free port for SSH forwarding."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    def _setup_ssh_config(self, ssh_port: int, container_name: str = None) -> Optional[str]:
        """Create SSH configuration for VS Code remote connection."""
        try:
            ssh_dir = os.path.expanduser("~/.ssh")
            os.makedirs(ssh_dir, exist_ok=True)

            ssh_config_path = os.path.join(ssh_dir, "config")
            host_entry = f"""
# LichOS CLI Development Container ({container_name if container_name else 'default'})
Host {container_name}
    HostName localhost
    Port {ssh_port}
    User root
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    PasswordAuthentication yes
"""

            existing_config = ""
            if os.path.exists(ssh_config_path):
                with open(ssh_config_path, encoding="utf-8") as f:
                    existing_config = f.read()

            lines = existing_config.split("\n")
            filtered_lines = []
            skip_block = False

            for line in lines:
                if line.strip().startswith(f"Host {container_name}"):
                    skip_block = True
                    continue
                elif line.strip().startswith("Host ") and skip_block:
                    skip_block = False
                elif line.strip().startswith("# LichOS CLI Development Container"):
                    skip_block = True
                    continue

                if not skip_block:
                    filtered_lines.append(line)

            new_config = "\n".join(filtered_lines).rstrip() + host_entry + "\n"

            with open(ssh_config_path, "w", encoding="utf-8") as f:
                f.write(new_config)

            logger.info("Updated SSH config at %s", ssh_config_path)
            return ssh_config_path

        except OSError as e:
            logger.error("Failed to setup SSH config: %s", e)
            return None
