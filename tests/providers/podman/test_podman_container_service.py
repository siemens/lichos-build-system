# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import Mock, patch

import pytest

from lichoscli.core.services import ContainerConfig
from lichoscli.providers.podman import PodmanContainerService


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


class TestPodmanContainerService:
    def setup_method(self):
        self.svc = PodmanContainerService()

    def test_command_is_podman(self):
        assert self.svc.command == "podman"

    def test_is_a_container_service(self):
        from lichoscli.core.services import ContainerService
        assert isinstance(self.svc, ContainerService)

    def test_build_run_command_includes_uidmap(self, cfg):
        cmd = self.svc.build_run_command(cfg)
        assert cmd[:3] == ["podman", "run", "--name"]
        # The uidmap quartet is always present
        assert "--user" in cmd
        assert cmd[cmd.index("--user") + 1] == "root"
        for opt in ("--uidmap",):
            assert cmd.count(opt) == 4
        # Sanity: expected mappings are present
        for mapping in ("0:1:1", "1000:0:1", "1:2:999", "1001:1001:64535"):
            assert mapping in cmd
        # No docker-only artefacts
        assert "--user" in cmd and "root" in cmd
        assert cmd[-4:-1] == ["debian:12", "/bin/bash", "-c"] or cmd[-3:] == ["debian:12", "/bin/bash", "-c"]

    @patch("subprocess.run")
    def test_pull_image_invokes_podman_pull(self, mock_run):
        mock_run.return_value.returncode = 0
        rc = self.svc.pull_image("debian:12")
        assert rc == 0
        mock_run.assert_called_once_with(["podman", "pull", "debian:12"], check=False)

    @patch("subprocess.run")
    def test_stop_container_invokes_podman_stop(self, mock_run):
        mock_run.return_value.returncode = 0
        assert self.svc.stop_container("c1") is True
        args = mock_run.call_args.args[0]
        assert args[:2] == ["podman", "stop"]

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
        # The final run command starts with `podman`
        run_call_args = mock_run.call_args_list[-1].args[0]
        assert run_call_args[0] == "podman"
        assert "--uidmap" in run_call_args
