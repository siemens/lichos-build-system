# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

from unittest.mock import patch

import pytest

from lichoscli.commands.setup import SetupCommand


@pytest.fixture
def setup_command(mock_di_container, mock_args):
    args = mock_args()
    return SetupCommand(mock_di_container, args)


def test_setup_saves_config(setup_command):
    """Test that setup prompts for host and token then saves config."""
    setup_command.ui.prompts.text_input.return_value = "gitlab.example.com"
    setup_command.ui.prompts.secret_input.return_value = "my-token"

    with patch("lichoscli.commands.setup.UserConfigStore") as mock_store:
        mock_store.read.return_value = {"hosts": {}}
        mock_store.get_token.return_value = None
        mock_store.config_path.return_value = "/home/user/.config/lichos/config.yml"
        result = setup_command.execute()

    assert result == 0
    mock_store.write.assert_called_once_with("gitlab.example.com", "my-token")


def test_setup_no_host_returns_error(setup_command):
    """Test that setup returns 1 when no hostname is provided."""
    setup_command.ui.prompts.text_input.return_value = ""

    with patch("lichoscli.commands.setup.UserConfigStore") as mock_store:
        mock_store.read.return_value = {"hosts": {}}
        result = setup_command.execute()

    assert result == 1
    mock_store.write.assert_not_called()


def test_setup_keeps_existing_token_when_blank(setup_command):
    """Test that leaving token blank retains the existing token for the host."""
    setup_command.ui.prompts.text_input.return_value = "gitlab.example.com"
    setup_command.ui.prompts.secret_input.return_value = ""

    with patch("lichoscli.commands.setup.UserConfigStore") as mock_store:
        mock_store.read.return_value = {
            "hosts": {"gitlab.example.com": {"token": "old-token"}},
        }
        mock_store.get_token.return_value = "old-token"
        mock_store.config_path.return_value = "/home/user/.config/lichos/config.yml"
        result = setup_command.execute()

    assert result == 0
    mock_store.write.assert_called_once_with("gitlab.example.com", "old-token")


def test_setup_normalizes_host_url(setup_command):
    """Test that a host provided as a full URL is normalized to just the hostname."""
    setup_command.ui.prompts.text_input.return_value = "https://gitlab.example.com"
    setup_command.ui.prompts.secret_input.return_value = "token"

    with patch("lichoscli.commands.setup.UserConfigStore") as mock_store:
        mock_store.read.return_value = {"hosts": {}}
        mock_store.get_token.return_value = None
        mock_store.config_path.return_value = "/home/user/.config/lichos/config.yml"
        result = setup_command.execute()

    assert result == 0
    mock_store.write.assert_called_once_with("gitlab.example.com", "token")
