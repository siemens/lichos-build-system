"""
Integration tests for the 'create' command.
"""

from unittest.mock import patch, Mock

from lichoscli.commands.create import CreateCommand
from lichoscli.utils import CI_DEFAULT_PIPELINE_NAME
from tests.fixtures import TestConstants, create_mock_args


class TestCreateCommandIntegration:
    """Integration tests for the 'create' command"""

    def setup_method(self):
        """Set up test fixtures, mock objects"""
        # Initialize test data
        self.package_name = "build-test-package"
        self.branch_name = "main"
        self.package_type = CI_DEFAULT_PIPELINE_NAME

        # Mock package
        self.mock_package = Mock()
        self.mock_package.name = self.package_name
        self.mock_package.default_branch = self.branch_name
        self.mock_package.ssh_url_to_repo = f"git@gitlab.example.com:{TestConstants.DEFAULT_GROUP_PATH}/{self.package_name}.git"
        # Add name property to fix 'str' object has no attribute 'name' error
        type(self.mock_package).name = self.package_name

        # Set up patches for mocking
        self.patches = []

        # Mock PkgGroupHandler
        self.pkg_handler_patcher = patch("lichoscli.pkg.PkgGroupHandler")
        self.mock_pkg_handler_class = self.pkg_handler_patcher.start()
        self.mock_pkg_handler = self.mock_pkg_handler_class.return_value
        self.mock_pkg_handler.group_rpath = TestConstants.DEFAULT_GROUP_PATH
        self.patches.append(self.pkg_handler_patcher)

        # Mock methods in CreateCommand
        self.check_local_exists_patcher = patch(
            "lichoscli.commands.create.CreateCommand.check_local_package_exists"
        )
        self.mock_check_local = self.check_local_exists_patcher.start()
        self.mock_check_local.return_value = False  # Package doesn't exist locally
        self.patches.append(self.check_local_exists_patcher)

        self.check_remote_exists_patcher = patch(
            "lichoscli.commands.create.CreateCommand.check_remote_package_exists"
        )
        self.mock_check_remote = self.check_remote_exists_patcher.start()
        self.mock_check_remote.return_value = False  # Package doesn't exist remotely
        self.patches.append(self.check_remote_exists_patcher)

        self.create_package_patcher = patch(
            "lichoscli.commands.create.CreateCommand.create_package"
        )
        self.mock_create_package = self.create_package_patcher.start()
        self.mock_create_package.return_value = self.mock_package
        self.patches.append(self.create_package_patcher)

        self.protect_branch_patcher = patch(
            "lichoscli.commands.create.CreateCommand.protect_branch"
        )
        self.mock_protect_branch = self.protect_branch_patcher.start()
        self.mock_protect_branch.return_value = True
        self.patches.append(self.protect_branch_patcher)

        self.init_repo_patcher = patch(
            "lichoscli.commands.create.CreateCommand.initialize_package_repository"
        )
        self.mock_init_repo = self.init_repo_patcher.start()
        # Create a mock author object with name and email attributes
        mock_author = Mock()
        mock_author.name = "Test Author"
        mock_author.email = "test@example.com"
        self.mock_init_repo.return_value = mock_author
        self.patches.append(self.init_repo_patcher)

        # Mock BuildUtils.get_package_name
        self.get_package_name_patcher = patch(
            "lichoscli.utils.BuildUtils.get_package_name",
            return_value=self.package_name,
        )
        self.get_package_name_patcher.start()
        self.patches.append(self.get_package_name_patcher)

    def teardown_method(self):
        """Clean up after each test"""
        for p in self.patches:
            p.stop()

    def test_create_package_success(self):
        """Test successful package creation"""
        # Create arguments for the create command
        args = create_mock_args(
            package=self.package_name, type=self.package_type, branch=self.branch_name, subgroup=""
        )

        # Execute the command
        create_cmd = CreateCommand(self.mock_pkg_handler, args)
        result = create_cmd.execute()

        # Verify checks were performed
        self.mock_check_local.assert_called_once_with(self.package_name)
        self.mock_check_remote.assert_called_once_with(
            self.mock_pkg_handler, self.package_name
        )

        # Verify package was created
        self.mock_create_package.assert_called_once_with(
            self.mock_pkg_handler,
            self.package_name,
            self.branch_name,
            self.package_type,
            ''
        )

        # Verify branch protection was set
        self.mock_protect_branch.assert_called_once_with(
            self.mock_package, self.branch_name
        )

        # Verify repository was initialized
        self.mock_init_repo.assert_called_once_with(
            self.mock_package, self.package_name
        )

        # Check return code
        assert result == 0

    def test_create_package_local_exists(self):
        """Test package creation when package already exists locally"""
        # Configure mock to indicate package exists locally
        self.mock_check_local.return_value = True

        # Create arguments for the create command
        args = create_mock_args(
            package=self.package_name, type=self.package_type, branch=self.branch_name
        )

        # Execute the command
        create_cmd = CreateCommand(self.mock_pkg_handler, args)
        result = create_cmd.execute()

        # Verify only local check was performed
        self.mock_check_local.assert_called_once_with(self.package_name)

        # Verify no further actions were taken
        self.mock_check_remote.assert_not_called()
        self.mock_create_package.assert_not_called()
        self.mock_protect_branch.assert_not_called()
        self.mock_init_repo.assert_not_called()

        # Check return code (failure)
        assert result == 1

    def test_create_package_remote_exists(self):
        """Test package creation when package already exists remotely"""
        # Configure mocks to indicate package exists remotely but not locally
        self.mock_check_local.return_value = False
        self.mock_check_remote.return_value = True

        # Create arguments for the create command
        args = create_mock_args(
            package=self.package_name, type=self.package_type, branch=self.branch_name
        )

        # Execute the command
        create_cmd = CreateCommand(self.mock_pkg_handler, args)
        result = create_cmd.execute()

        # Verify checks were performed
        self.mock_check_local.assert_called_once_with(self.package_name)
        self.mock_check_remote.assert_called_once_with(
            self.mock_pkg_handler, self.package_name
        )

        # Verify no further actions were taken
        self.mock_create_package.assert_not_called()
        self.mock_protect_branch.assert_not_called()
        self.mock_init_repo.assert_not_called()

        # Check return code (failure)
        assert result == 1

    def test_create_package_creation_failed(self):
        """Test case when package creation fails"""
        # Configure mock to indicate package creation failed
        self.mock_create_package.return_value = None

        # Create arguments for the create command
        args = create_mock_args(
            package=self.package_name, type=self.package_type, branch=self.branch_name, subgroup="subgroup"
        )

        # Execute the command
        create_cmd = CreateCommand(self.mock_pkg_handler, args)
        result = create_cmd.execute()

        # Verify checks and creation attempt were performed
        self.mock_check_local.assert_called_once_with(self.package_name)
        self.mock_check_remote.assert_called_once_with(
            self.mock_pkg_handler, self.package_name
        )
        self.mock_create_package.assert_called_once_with(
            self.mock_pkg_handler,
            self.package_name,
            self.branch_name,
            self.package_type,
            'subgroup'
        )

        # Verify no further actions were taken
        self.mock_protect_branch.assert_not_called()
        self.mock_init_repo.assert_not_called()

        # Check return code (failure)
        assert result == 1
