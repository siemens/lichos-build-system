# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

import pytest

from lichoscli.core.services import ContainerConfig
from lichoscli.providers.docker import DockerContainerService


@pytest.fixture
def cfg():
    return ContainerConfig(
        image="debian:12",
        name="build-abc",
        command="make",
        working_dir="/work",
        environment={"FOO": "bar"},
        volumes=["/src:/src"],
        env_file=None,
        detached=False,
        interactive=False,
        remove_on_exit=True,
        privileged=False,
    )


class TestDockerContainerService:
    def setup_method(self):
        self.svc = DockerContainerService()

    def test_command_is_docker(self):
        assert self.svc.command == "docker"

    def test_build_run_command_minimal(self, cfg):
        cfg.environment = {}
        cfg.volumes = []
        cmd = self.svc.build_run_command(cfg)
        assert cmd[:3] == ["docker", "run", "--name"]
        assert cmd[3] == "build-abc"
        assert "--rm" in cmd
        assert cmd[-4:] == ["debian:12", "/bin/bash", "-c", "make"]
        # No podman-specific options
        assert "--uidmap" not in cmd

    def test_build_run_command_passes_all_options(self, cfg):
        cfg.network = "host"
        cfg.platform = "linux/amd64"
        cfg.privileged = True
        cfg.env_file = "/tmp/env"
        cmd = self.svc.build_run_command(cfg)
        assert "--network" in cmd and "host" in cmd
        assert "--platform" in cmd and "linux/amd64" in cmd
        assert "--privileged" in cmd
        assert "--env-file" in cmd and "/tmp/env" in cmd

    @patch("subprocess.run")
    def test_pull_image_invokes_docker_pull(self, mock_run):
        mock_run.return_value.returncode = 0
        rc = self.svc.pull_image("debian:12")
        assert rc == 0
        mock_run.assert_called_once_with(["docker", "pull", "debian:12"], check=False)

    @patch("subprocess.run")
    def test_stop_container_invokes_docker_stop(self, mock_run):
        mock_run.return_value.returncode = 0
        assert self.svc.stop_container("c1") is True
        args = mock_run.call_args.args[0]
        assert args[:2] == ["docker", "stop"]
        assert args[2] == "c1"

    @patch("subprocess.run")
    def test_remove_container_invokes_docker_rm(self, mock_run):
        mock_run.return_value.returncode = 0
        assert self.svc.remove_container("c1") is True
        args = mock_run.call_args.args[0]
        assert args[:2] == ["docker", "rm"]

    @patch("subprocess.run")
    def test_container_exists(self, mock_run):
        mock_run.return_value.stdout = "abc123\n"
        mock_run.return_value.returncode = 0
        assert self.svc.container_exists("c1") is True
        args = mock_run.call_args.args[0]
        assert args[:2] == ["docker", "ps"]

    @patch("subprocess.run")
    def test_container_missing(self, mock_run):
        mock_run.return_value.stdout = ""
        assert self.svc.container_exists("c1") is False

    @patch("subprocess.run")
    def test_run_container_removes_existing_first(self, mock_run):
        mock_run.side_effect = [
            Mock(stdout="id1\n"),  # container_exists check
            Mock(returncode=0),    # stop
            Mock(returncode=0, stderr=b""),  # remove
            Mock(returncode=0),    # run
        ]
        cfg = ContainerConfig(
            image="img", name="c1", command="hi", working_dir="/w",
            environment={}, volumes=[],
        )
        result = self.svc.run_container(cfg)
        assert result.return_code == 0
        assert result.container_name == "c1"
