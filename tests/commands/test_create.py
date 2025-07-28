import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from lichoscli.commands.create import CreateCommand
from lichoscli.commands.base import CommandRegister
from tests import fixtures


class TestCreateCommand(unittest.TestCase):
    def setUp(self):
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.type = "gbp"
        self.args.branch = "main"
        self.args.subgroup = ""

        self.command = CreateCommand(self.pkg_handler, self.args)

    def tearDown(self):
        if os.path.exists("test-package"):
            import shutil

            shutil.rmtree("test-package")

    def test_command_initialization_sets_correct_attributes(self):
        self.assertEqual(self.command.package_name, "test-package")
        self.assertEqual(self.command.package_type, "gbp")
        self.assertEqual(self.command.branch, "main")
        self.assertEqual(self.command.pkg_group_handler, self.pkg_handler)

    @patch("os.path.exists")
    def test_check_local_package_exists_true(self, mock_exists):
        mock_exists.return_value = True
        result = CreateCommand.check_local_package_exists("test-package")
        self.assertTrue(result)
        mock_exists.assert_called_once_with("test-package")

    @patch("os.path.exists")
    def test_check_local_package_exists_false(self, mock_exists):
        mock_exists.return_value = False
        result = CreateCommand.check_local_package_exists("test-package")
        self.assertFalse(result)
        mock_exists.assert_called_once_with("test-package")

    def test_check_remote_package_exists_true(self):
        mock_pkg_handler = fixtures.create_full_mock_pkg_handler()
        mock_pkg_handler.get_package.return_value = fixtures.create_mock_project()

        result = CreateCommand.check_remote_package_exists(
            mock_pkg_handler, "existing-package"
        )
        self.assertTrue(result)
        mock_pkg_handler.get_package.assert_called_once_with("existing-package")

    def test_check_remote_package_exists_false(self):
        mock_pkg_handler = fixtures.create_full_mock_pkg_handler()
        mock_pkg_handler.get_package.return_value = None

        result = CreateCommand.check_remote_package_exists(
            mock_pkg_handler, "new-package"
        )
        self.assertFalse(result)
        mock_pkg_handler.get_package.assert_called_once_with("new-package")

    def test_create_package_success(self):
        mock_package = fixtures.create_mock_project()
        mock_pkg_handler = fixtures.create_full_mock_pkg_handler()
        mock_pkg_handler.add_package.return_value = mock_package

        result = CreateCommand.create_package(
            mock_pkg_handler, "test-package", "main", "gbp", subgroup=""
        )
        self.assertEqual(result, mock_package)
        mock_pkg_handler.add_package.assert_called_once_with(
            package_name="test-package",
            branch="main",
            package_type="gbp",
            access_level="enabled",
            subgroup=""
        )
    
    def test_create_subpackage_success(self):
        mock_package = fixtures.create_mock_project(namespace={"full_path": "test-group/pkg/subgroup", "path": "subgroup"})
        mock_pkg_handler = fixtures.create_full_mock_pkg_handler(subgroup="subgroup")
        mock_pkg_handler.add_package.return_value = mock_package

        result = CreateCommand.create_package(
            mock_pkg_handler, "test-package", "main", "gbp", "subgroup"
        )
        self.assertEqual(result, mock_package)
        mock_pkg_handler.add_package.assert_called_once_with(
            package_name="test-package",
            branch="main",
            package_type="gbp",
            access_level="enabled",
            subgroup="subgroup"
        )

    def test_create_package_failure(self):
        mock_pkg_handler = fixtures.create_full_mock_pkg_handler()
        mock_pkg_handler.add_package.return_value = None
        mock_pkg_handler.group_rpath = "test-group"

        result = CreateCommand.create_package(
            mock_pkg_handler, "test-package", "main", "gbp", ""
        )
        self.assertIsNone(result)

    @patch("lichoscli.commands.create.GitUtils.delete_main_from_branch_name")
    def test_protect_branch_success(self, mock_delete_main):
        mock_package = Mock()
        mock_package.protectedbranches.create.return_value = True
        mock_delete_main.return_value = "formatted-branch"

        result = CreateCommand.protect_branch(mock_package, "main")
        self.assertTrue(result)
        mock_package.protectedbranches.create.assert_called_once_with(
            {"name": "formatted-branch"}
        )

    @patch("lichoscli.commands.create.GitUtils.delete_main_from_branch_name")
    def test_protect_branch_failure(self, mock_delete_main):
        mock_package = Mock()
        mock_package.protectedbranches.create.side_effect = Exception("Failed")
        mock_delete_main.return_value = "formatted-branch"

        result = CreateCommand.protect_branch(mock_package, "main")
        self.assertFalse(result)

    @patch("lichoscli.commands.create.Repo.clone_from")
    def test_initialize_package_repository(self, mock_git):
        mock_package = Mock()
        mock_package.ssh_url_to_repo = "git@example.com:test/repo.git"

        mock_repo = Mock()
        mock_author = Mock()
        mock_commit = Mock()
        mock_commit.author = mock_author
        mock_repo.index.commit.return_value = mock_commit
        mock_git.return_value = mock_repo

        result = CreateCommand.initialize_package_repository(
            mock_package, "test-package"
        )
        self.assertEqual(result, mock_author)
        mock_git.assert_called_once_with(
            "git@example.com:test/repo.git", "test-package"
        )

    @patch("os.makedirs")
    @patch("builtins.open", create=True)
    def test_create_debian_package_template(self, mock_open, mock_makedirs):
        mock_author = fixtures.create_mock_author()

        CreateCommand.create_debian_package_template("test-package", mock_author)

        mock_makedirs.assert_called()

        self.assertEqual(mock_open.call_count, 3)

    @patch("builtins.open", create=True)
    def test_add_default_debian_control(self, mock_open):
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_author = fixtures.create_mock_author()

        CreateCommand.add_default_debian_control(
            "test-package", mock_author, "/path/to/control"
        )

        mock_open.assert_called_once_with("/path/to/control", "w", encoding="utf-8")
        written_content = mock_file.write.call_args[0][0]
        self.assertIn("test-package", written_content)
        self.assertIn("Test Author", written_content)
        self.assertIn("test@example.com", written_content)

    @patch("builtins.open", create=True)
    def test_add_default_debian_rules(self, mock_open):
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        CreateCommand.add_default_debian_rules("/path/to/rules")

        mock_open.assert_called_once_with("/path/to/rules", "w", encoding="utf-8")
        written_content = mock_file.write.call_args[0][0]
        self.assertIn("#!/usr/bin/make -f", written_content)
        self.assertIn("dh $@", written_content)

    @patch.object(CreateCommand, "check_local_package_exists")
    def test_execute_local_package_exists(self, mock_check_local):
        mock_check_local.return_value = True

        result = self.command.execute()
        self.assertEqual(result, 1)
        mock_check_local.assert_called_once_with("test-package")

    @patch.object(CreateCommand, "check_local_package_exists")
    @patch.object(CreateCommand, "check_remote_package_exists")
    def test_execute_remote_package_exists(self, mock_check_remote, mock_check_local):
        mock_check_local.return_value = False
        mock_check_remote.return_value = True

        result = self.command.execute()
        self.assertEqual(result, 1)
        mock_check_remote.assert_called_once_with(self.pkg_handler, "test-package")

    @patch.object(CreateCommand, "check_local_package_exists")
    @patch.object(CreateCommand, "check_remote_package_exists")
    @patch.object(CreateCommand, "create_package")
    @patch.object(CreateCommand, "protect_branch")
    @patch.object(CreateCommand, "initialize_package_repository")
    @patch.object(CreateCommand, "create_debian_package_template")
    def test_execute_success(
        self,
        mock_create_debian,
        mock_init_repo,
        mock_protect,
        mock_create_pkg,
        mock_check_remote,
        mock_check_local,
    ):

        mock_check_local.return_value = False
        mock_check_remote.return_value = False

        mock_package = fixtures.create_mock_project()
        mock_create_pkg.return_value = mock_package
        mock_protect.return_value = True

        mock_author = fixtures.create_mock_author()
        mock_init_repo.return_value = mock_author

        result = self.command.execute()
        self.assertEqual(result, 0)

        mock_check_local.assert_called_once_with("test-package")
        mock_check_remote.assert_called_once_with(self.pkg_handler, "test-package")
        mock_create_pkg.assert_called_once_with(
            self.pkg_handler, "test-package", "main", "gbp", ""
        )
        mock_protect.assert_called_once_with(mock_package, "main")
        mock_init_repo.assert_called_once_with(mock_package, "test-package")
        mock_create_debian.assert_called_once_with("test-package", mock_author)

    @patch.object(CreateCommand, "check_local_package_exists")
    @patch.object(CreateCommand, "check_remote_package_exists")
    @patch.object(CreateCommand, "create_package")
    def test_execute_create_package_fails(
        self, mock_create_pkg, mock_check_remote, mock_check_local
    ):
        mock_check_local.return_value = False
        mock_check_remote.return_value = False
        mock_create_pkg.return_value = None

        result = self.command.execute()
        self.assertEqual(result, 1)

    @patch.object(CreateCommand, "check_local_package_exists")
    @patch.object(CreateCommand, "check_remote_package_exists")
    @patch.object(CreateCommand, "create_package")
    @patch.object(CreateCommand, "protect_branch")
    def test_execute_protect_branch_fails(
        self, mock_protect, mock_create_pkg, mock_check_remote, mock_check_local
    ):
        mock_check_local.return_value = False
        mock_check_remote.return_value = False
        mock_package = fixtures.create_mock_project()
        mock_create_pkg.return_value = mock_package
        mock_protect.return_value = False

        result = self.command.execute()
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
