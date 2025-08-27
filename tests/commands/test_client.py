import pytest
import os
import yaml
from unittest.mock import patch, mock_open, MagicMock
import gitlab

from lichoscli.providers.gitlab.client import GitLabClientFactory


class TestGitLabClientFactory:

    def test_init_with_host(self):
        """Test initialization with a specific host."""
        factory = GitLabClientFactory(host="gitlab.example.com")
        assert factory.host == "gitlab.example.com"

    def test_init_without_host(self):
        """Test initialization without host (uses default)."""
        factory = GitLabClientFactory()
        assert factory.host is None

    def test_ensure_url_scheme_with_https(self):
        """Test URL scheme handling when https:// is already present."""
        factory = GitLabClientFactory()
        url = factory._ensure_url_scheme("https://gitlab.example.com")
        assert url == "https://gitlab.example.com"

    def test_ensure_url_scheme_with_http(self):
        """Test URL scheme handling when http:// is present."""
        factory = GitLabClientFactory()
        url = factory._ensure_url_scheme("http://gitlab.example.com")
        assert url == "http://gitlab.example.com"

    def test_ensure_url_scheme_without_scheme(self):
        """Test URL scheme handling when no scheme is present."""
        factory = GitLabClientFactory()
        url = factory._ensure_url_scheme("gitlab.example.com")
        assert url == "https://gitlab.example.com"

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_init_from_glab_config_success_default_host(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists
    ):
        """Test successful initialization from glab config with default host."""

        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_config = {
            "hosts": {"gitlab.com": {"token": "test-token-123", "user": "testuser"}}
        }
        mock_yaml.return_value = mock_config
        mock_gl_instance = MagicMock()
        mock_gitlab.return_value = mock_gl_instance

        factory = GitLabClientFactory()
        result = factory._init_from_glab_config()

        mock_gitlab.assert_called_once_with(
            url="https://gitlab.com", private_token="test-token-123", api_version="4"
        )
        mock_gl_instance.auth.assert_called_once()
        assert result == mock_gl_instance

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_init_from_glab_config_success_specific_host(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists
    ):
        """Test successful initialization from glab config with specific host."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_config = {
            "hosts": {
                "gitlab.com": {
                    "token": "token-1",
                },
                "gitlab.example.com": {
                    "token": "token-2",
                },
            }
        }
        mock_yaml.return_value = mock_config
        mock_gl_instance = MagicMock()
        mock_gitlab.return_value = mock_gl_instance

        factory = GitLabClientFactory()
        result = factory._init_from_glab_config(host="gitlab.example.com")

        mock_gitlab.assert_called_once_with(
            url="https://gitlab.example.com", private_token="token-2", api_version="4"
        )
        mock_gl_instance.auth.assert_called_once()
        assert result == mock_gl_instance

    @patch("os.path.exists")
    def test_init_from_glab_config_file_not_found(self, mock_exists):
        """Test FileNotFoundError when config file doesn't exist."""
        mock_exists.return_value = False

        factory = GitLabClientFactory()

        with pytest.raises(FileNotFoundError, match="glab config not found"):
            factory._init_from_glab_config()

    @patch("os.path.exists")
    def test_init_from_glab_config_checks_both_paths(self, mock_exists):
        """Test that both possible config paths are checked."""
        mock_exists.return_value = False

        factory = GitLabClientFactory()

        with pytest.raises(FileNotFoundError):
            factory._init_from_glab_config()

        expected_calls = [
            os.path.expanduser("~/.config/glab-cli/config.yml"),
            os.path.expanduser("~/AppData/Local/glab-cli/config.yml"),
        ]
        actual_calls = [call[0][0] for call in mock_exists.call_args_list]
        assert actual_calls == expected_calls

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_init_from_glab_config_yaml_error(self, mock_yaml, mock_file, mock_exists):
        """Test YAML parsing error handling."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_yaml.side_effect = yaml.YAMLError("Invalid YAML")

        factory = GitLabClientFactory()

        with pytest.raises(yaml.YAMLError):
            factory._init_from_glab_config()

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_init_from_glab_config_no_hosts(self, mock_yaml, mock_file, mock_exists):
        """Test ValueError when no hosts are found in config."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_yaml.return_value = {"hosts": {}}

        factory = GitLabClientFactory()

        with pytest.raises(ValueError, match="No hosts found in glab config"):
            factory._init_from_glab_config()

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_init_from_glab_config_host_not_found(
        self, mock_yaml, mock_file, mock_exists
    ):
        """Test ValueError when specified host is not found in config."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_config = {"hosts": {"gitlab.com": {"token": "test-token"}}}
        mock_yaml.return_value = mock_config

        factory = GitLabClientFactory()

        with pytest.raises(
            ValueError, match="Host nonexistent.com not found in glab config"
        ):
            factory._init_from_glab_config(host="nonexistent.com")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_init_from_glab_config_auth_error(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists
    ):
        """Test GitLab authentication error handling."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_config = {"hosts": {"gitlab.com": {"token": "invalid-token"}}}
        mock_yaml.return_value = mock_config
        mock_gl_instance = MagicMock()
        mock_gl_instance.auth.side_effect = gitlab.exceptions.GitlabAuthenticationError(
            "Invalid token"
        )
        mock_gitlab.return_value = mock_gl_instance

        factory = GitLabClientFactory()

        with pytest.raises(gitlab.exceptions.GitlabAuthenticationError):
            factory._init_from_glab_config()

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_init_from_glab_config_general_exception(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists
    ):
        """Test general exception handling."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_config = {"hosts": {"gitlab.com": {"token": "test-token"}}}
        mock_yaml.return_value = mock_config
        mock_gitlab.side_effect = Exception("Unexpected error")

        factory = GitLabClientFactory()

        with pytest.raises(Exception, match="Unexpected error"):
            factory._init_from_glab_config()

    @patch.object(GitLabClientFactory, "_init_from_glab_config")
    def test_create_with_host(self, mock_init):
        """Test create method with host."""
        mock_gl_instance = MagicMock()
        mock_init.return_value = mock_gl_instance

        factory = GitLabClientFactory(host="gitlab.example.com")
        result = factory.create()

        mock_init.assert_called_once_with("gitlab.example.com")
        assert result == mock_gl_instance

    @patch.object(GitLabClientFactory, "_init_from_glab_config")
    def test_create_without_host(self, mock_init):
        """Test create method without host."""
        mock_gl_instance = MagicMock()
        mock_init.return_value = mock_gl_instance

        factory = GitLabClientFactory()
        result = factory.create()

        mock_init.assert_called_once_with(None)
        assert result == mock_gl_instance

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_uses_windows_config_path(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists
    ):
        """Test that Windows config path is used when Unix path doesn't exist."""

        def exists_side_effect(path):
            return "AppData" in path

        mock_exists.side_effect = exists_side_effect
        mock_config = {"hosts": {"gitlab.com": {"token": "test-token"}}}
        mock_yaml.return_value = mock_config
        mock_gl_instance = MagicMock()
        mock_gitlab.return_value = mock_gl_instance

        factory = GitLabClientFactory()
        factory._init_from_glab_config()

        mock_file.assert_called_once()
        call_args = mock_file.call_args[0][0]
        assert "AppData" in call_args

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_host_with_existing_scheme(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists
    ):
        """Test initialization with host that already has a scheme."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_config = {"hosts": {"http://gitlab.example.com": {"token": "test-token"}}}
        mock_yaml.return_value = mock_config
        mock_gl_instance = MagicMock()
        mock_gitlab.return_value = mock_gl_instance

        factory = GitLabClientFactory()
        factory._init_from_glab_config(host="http://gitlab.example.com")

        mock_gitlab.assert_called_once_with(
            url="http://gitlab.example.com", private_token="test-token", api_version="4"
        )

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_file_encoding_utf8(self, mock_yaml, mock_file, mock_exists):
        """Test that config file is opened with UTF-8 encoding."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_yaml.return_value = {"hosts": {}}

        factory = GitLabClientFactory()

        with pytest.raises(ValueError):  # Will fail due to empty hosts, but that's fine
            factory._init_from_glab_config()

        mock_file.assert_called_once()
        call_kwargs = mock_file.call_args[1]
        assert call_kwargs["encoding"] == "utf-8"


@pytest.fixture
def sample_config():
    """Sample glab config for testing."""
    return {
        "hosts": {
            "gitlab.com": {
                "token": "glpat-xxxxxxxxxxxxxxxxxxxx",
                "user": "testuser",
                "git_protocol": "https",
            },
            "gitlab.example.com": {
                "token": "glpat-yyyyyyyyyyyyyyyyyyyy",
                "user": "exampleuser",
                "git_protocol": "ssh",
            },
        }
    }


class TestIntegration:
    """Integration tests for more complex scenarios."""

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("gitlab.Gitlab")
    def test_end_to_end_flow(
        self, mock_gitlab, mock_yaml, mock_file, mock_exists, sample_config
    ):
        """Test the complete flow from factory creation to GitLab client."""
        mock_exists.side_effect = lambda path: path.endswith("config.yml")
        mock_yaml.return_value = sample_config
        mock_gl_instance = MagicMock()
        mock_gitlab.return_value = mock_gl_instance

        factory = GitLabClientFactory(host="gitlab.example.com")
        client = factory.create()

        assert client == mock_gl_instance
        mock_gitlab.assert_called_once_with(
            url="https://gitlab.example.com",
            private_token="glpat-yyyyyyyyyyyyyyyyyyyy",
            api_version="4",
        )
        mock_gl_instance.auth.assert_called_once()
