import os
import unittest
from unittest.mock import Mock, patch, mock_open
from lichoscli.commands.build import BuildCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestBuildCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.architecture = "x86_64"
        self.args.script = None
        self.args.shell = False
        self.args.enable_cross = False
        self.args.profile = None

        self.mock_repo = fixtures.create_mock_git_repo()
        self.mock_package = fixtures.create_mock_project()

        self.pkg_handler.get_package.return_value = self.mock_package
        self.pkg_handler.group_rpath = "test-group"
        self.args.pkg_group = "test-group/pkg"

    @patch("git.Repo")
    @patch("lichoscli.commands.build.GitUtils")
    @patch("os.uname")
    def test_command_initialization_sets_correct_attributes(
        self, mock_uname, mock_git_utils, mock_git_repo
    ):
        """Test that command initialization sets correct attributes."""
        mock_uname.return_value.machine = "x86_64"
        mock_git_repo.return_value = self.mock_repo
        mock_git_utils.get_branch.return_value = "main"
        mock_git_utils.get_ref_slug.return_value = "main-slug"

        command = BuildCommand(self.pkg_handler, self.args)

        self.assertEqual(command.package, self.mock_package)
        self.assertEqual(command.group, "test-group/pkg")
        self.assertEqual(command.architecture, "amd64")
        self.assertEqual(command.platform, "linux/amd64")
        self.assertEqual(command.shell, False)
        self.assertEqual(command.enable_cross, False)
        self.assertEqual(command.build_arch, "amd64")

    def test_normalize_architecture_maps_correctly(self):
        """Test architecture normalization mapping."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            command = BuildCommand(self.pkg_handler, self.args)

            self.assertEqual(command._normalize_architecture("x86_64"), "amd64")
            self.assertEqual(command._normalize_architecture("aarch64"), "arm64")
            self.assertEqual(command._normalize_architecture("unknown"), "unknown")

    @patch("git.Repo")
    @patch("lichoscli.commands.build.GitUtils")
    def test_determine_project_dir_non_shell_mode(self, _, __):
        """Test project directory determination in non-shell mode."""
        self.args.shell = False
        command = BuildCommand(self.pkg_handler, self.args)

        project_dir = command._determine_project_dir(False)
        # Should be a randomized version of "/build" path
        self.assertNotEqual(project_dir, "/build")
        self.assertTrue(project_dir.startswith("/"))

    @patch("git.Repo")
    @patch("lichoscli.commands.build.GitUtils")
    def test_build_environment_basic(self, mock_git_utils, mock_git_repo):
        """Test building basic environment variables."""
        mock_git_utils.get_branch.return_value = "main"
        mock_git_utils.get_ref_slug.return_value = "main-slug"
        self.pkg_handler.get_package_variables.return_value = {"CUSTOM_VAR": "value"}

        command = BuildCommand(self.pkg_handler, self.args)
        env = command._build_environment()

        expected_keys = [
            "CI_PROJECT_DIR",
            "CI_COMMIT_BRANCH",
            "CI_COMMIT_REF_NAME",
            "CI_COMMIT_REF_SLUG",
            "CI_PROJECT_NAMESPACE",
            "ARCHITECTURE",
            "CUSTOM_VAR",
        ]

        for key in expected_keys:
            self.assertIn(key, env)

        self.assertEqual(env["ARCHITECTURE"], "amd64")
        self.assertEqual(env["CI_COMMIT_BRANCH"], "main")
        self.assertEqual(env["CUSTOM_VAR"], "value")

    @patch("git.Repo")
    @patch("lichoscli.commands.build.GitUtils")
    def test_build_environment_with_cross_compilation(
        self, mock_git_utils, mock_git_repo
    ):
        """Test environment building with cross-compilation enabled."""
        self.args.enable_cross = True
        mock_git_utils.get_branch.return_value = "main"
        mock_git_utils.get_ref_slug.return_value = "main-slug"
        self.pkg_handler.get_package_variables.return_value = {}

        command = BuildCommand(self.pkg_handler, self.args)
        env = command._build_environment()

        self.assertIn("DEB_HOST_ARCH", env)
        self.assertEqual(env["DEB_HOST_ARCH"], "amd64")

    @patch("git.Repo")
    @patch("lichoscli.commands.build.GitUtils")
    def test_build_environment_with_profile(self, mock_git_utils, mock_git_repo):
        """Test environment building with build profile."""
        self.args.profile = "test-profile"
        mock_git_utils.get_branch.return_value = "main"
        mock_git_utils.get_ref_slug.return_value = "main-slug"
        self.pkg_handler.get_package_variables.return_value = {}

        command = BuildCommand(self.pkg_handler, self.args)
        env = command._build_environment()

        self.assertIn("DEB_BUILD_PROFILES", env)
        self.assertEqual(env["DEB_BUILD_PROFILES"], "test-profile")

    def test_get_cross_compilation_env(self):
        """Test cross-compilation environment variables."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            command = BuildCommand(self.pkg_handler, self.args)
            cross_env = command._get_cross_compilation_env()

            expected = {
                "ARCHITECTURE": command._normalize_architecture(
                    os.uname().machine
                ),  # normalized architecture
                "DEB_HOST_ARCH": "amd64",  # target architecture
            }
            self.assertEqual(cross_env, expected)

    def test_get_profile_env_with_profile(self):
        """Test profile environment variables when profile is set."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            self.args.profile = "test-profile"
            command = BuildCommand(self.pkg_handler, self.args)
            profile_env = command._get_profile_env()

            self.assertEqual(profile_env, {"DEB_BUILD_PROFILES": "test-profile"})

    def test_get_profile_env_without_profile(self):
        """Test profile environment variables when profile is not set."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            command = BuildCommand(self.pkg_handler, self.args)
            profile_env = command._get_profile_env()

            self.assertEqual(profile_env, {})

    @patch("lichoscli.commands.build.BuildUtils")
    @patch("lichoscli.commands.build.PkgGroupHandler")
    def test_prepare_build_environment_success(
        self, mock_pkg_handler_class, mock_build_utils
    ):
        """Test successful build environment preparation."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            # Setup mocks
            mock_tmpdir = "/tmp/test"
            mock_pkg_handler_class.get_job_artifacts.return_value = mock_tmpdir

            mock_env = {"TEST": "value"}
            mock_build_utils.update_environment_from_file.return_value = mock_env
            mock_build_utils.expand_var.return_value = mock_env

            mock_env_file = Mock()
            mock_build_utils.create_tmp_env_file.return_value = mock_env_file

            command = BuildCommand(self.pkg_handler, self.args)
            result = command._prepare_build_environment()

            self.assertEqual(result, mock_env_file)
            mock_pkg_handler_class.get_job_artifacts.assert_called_once()
            mock_build_utils.update_environment_from_file.assert_called_once()
            mock_build_utils.expand_var.assert_called_once()
            mock_build_utils.create_tmp_env_file.assert_called_once()

    @patch("lichoscli.commands.build.PkgGroupHandler")
    def test_prepare_build_environment_no_artifacts(self, mock_pkg_handler_class):
        """Test build environment preparation when artifacts are not available."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            mock_pkg_handler_class.get_job_artifacts.return_value = None

            command = BuildCommand(self.pkg_handler, self.args)
            result = command._prepare_build_environment()

            self.assertIsNone(result)

    def test_extract_docker_config_success(self):
        """Test successful Docker configuration extraction."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            command = BuildCommand(self.pkg_handler, self.args)

            # Create a mock env file
            env_content = "IMAGE=test:latest\nREPO_SETUP_CMD=setup\nBUILD_CMD=build\n"

            with patch("builtins.open", mock_open(read_data=env_content)):
                mock_env_file = Mock()
                mock_env_file.name = "test.env"

                config = command._extract_docker_config(mock_env_file)

                expected = {
                    "image": "test:latest",
                    "script": "setup ; build",
                    "env_file": mock_env_file,
                }

                self.assertEqual(config, expected)

    def test_extract_docker_config_missing_variables(self):
        """Test Docker configuration extraction with missing required variables."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            command = BuildCommand(self.pkg_handler, self.args)

            # Missing BUILD_CMD
            env_content = "IMAGE=test:latest\nREPO_SETUP_CMD=setup\n"

            with patch("builtins.open", mock_open(read_data=env_content)):
                mock_env_file = Mock()
                mock_env_file.name = "test.env"

                config = command._extract_docker_config(mock_env_file)

                self.assertIsNone(config)

    @patch("subprocess.run")
    @patch("lichoscli.commands.build.BuildUtils")
    @patch("os.unlink")
    def test_execute_success(self, mock_unlink, mock_build_utils, mock_subprocess):
        """Test successful command execution."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            # Setup all the mocks for the execution flow
            mock_env_file = Mock()
            mock_env_file.name = "test.env"

            command = BuildCommand(self.pkg_handler, self.args)

            # Mock the preparation methods
            with patch.object(
                command, "_prepare_build_environment", return_value=mock_env_file
            ), patch.object(
                command,
                "_extract_docker_config",
                return_value={
                    "image": "test:latest",
                    "script": "test script",
                    "env_file": mock_env_file,
                },
            ), patch.object(
                command, "_build_docker_command", return_value=["docker", "run"]
            ):

                mock_build_utils.pull_docker_image.return_value = 0
                mock_subprocess.return_value.returncode = 0

                result = command.execute()

                self.assertEqual(result, 0)
                mock_build_utils.pull_docker_image.assert_called_once()
                mock_subprocess.assert_called_once()
                mock_unlink.assert_called_once_with(mock_env_file.name)

    @patch("subprocess.run")
    @patch("lichoscli.commands.build.BuildUtils")
    @patch("os.unlink")
    def test_execute_docker_pull_failure(
        self, mock_unlink, mock_build_utils, mock_subprocess
    ):
        """Test command execution when Docker pull fails."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            mock_env_file = Mock()
            mock_env_file.name = "test.env"

            command = BuildCommand(self.pkg_handler, self.args)

            with patch.object(
                command, "_prepare_build_environment", return_value=mock_env_file
            ), patch.object(
                command,
                "_extract_docker_config",
                return_value={
                    "image": "test:latest",
                    "script": "test script",
                    "env_file": mock_env_file,
                },
            ):

                mock_build_utils.pull_docker_image.return_value = 1  # Failure

                result = command.execute()

                self.assertEqual(result, 1)
                mock_subprocess.assert_not_called()
                mock_unlink.assert_called_once_with(mock_env_file.name)

    @patch("os.unlink")
    def test_execute_prepare_environment_failure(self, mock_unlink):
        """Test command execution when environment preparation fails."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            command = BuildCommand(self.pkg_handler, self.args)

            with patch.object(command, "_prepare_build_environment", return_value=None):
                result = command.execute()

                self.assertEqual(result, 1)
                mock_unlink.assert_not_called()

    @patch("os.unlink")
    def test_execute_docker_config_extraction_failure(self, mock_unlink):
        """Test command execution when Docker config extraction fails."""
        with patch("git.Repo"), patch("lichoscli.commands.build.GitUtils"):
            mock_env_file = Mock()
            mock_env_file.name = "test.env"

            command = BuildCommand(self.pkg_handler, self.args)

            with patch.object(
                command, "_prepare_build_environment", return_value=mock_env_file
            ), patch.object(command, "_extract_docker_config", return_value=None):

                result = command.execute()

                self.assertEqual(result, 1)
                mock_unlink.assert_called_once_with(mock_env_file.name)
