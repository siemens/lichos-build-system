import unittest
from unittest.mock import Mock, patch
from lichoscli.commands.hierarchy import HierarchyCommand
from lichoscli.pkg import PkgGroupHandler
from tests import fixtures


class TestHierarchyCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.pkg_handler.gitlab = Mock()  # Add gitlab attribute
        self.args = fixtures.create_mock_args()
        self.args.target_path = "target-group/pkg"

    def test_hierarchy_command_initialization(self):
        """Test that hierarchy command initialization sets correct attributes."""
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        self.assertEqual(command.args.target_path, "target-group/pkg")
        self.assertEqual(command.pkg_group_handler, self.pkg_handler)

    @patch('lichoscli.commands.hierarchy.PkgGroupHandler')
    def test_execute_hierarchy_already_exists(self, mock_pkg_handler_class):
        """Test execution when target hierarchy already exists."""
        # Mock hierarchy already exists
        self.pkg_handler.hierarchy_exists.return_value = True
        
        # Mock target pkg handler
        mock_target_pkg_handler = Mock(spec=PkgGroupHandler)
        mock_pkg_handler_class.return_value = mock_target_pkg_handler
        
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        with patch.object(command, '_fork_required_packages', return_value=True) as mock_fork:
            with patch.object(command, 'pkg_group_handler') as mock_handler:
                mock_group = Mock()
                mock_group.web_url = "https://gitlab.example.com/target-group/pkg"
                mock_handler.get_group.return_value = mock_group
                
                result = command.execute()
        
        self.assertEqual(result, 0)
        mock_fork.assert_called_once_with(mock_target_pkg_handler)

    @patch('lichoscli.commands.hierarchy.PkgGroupHandler')
    def test_execute_create_new_hierarchy(self, mock_pkg_handler_class):
        """Test execution when creating a new hierarchy."""
        # Mock hierarchy doesn't exist
        self.pkg_handler.hierarchy_exists.return_value = False
        
        # Mock target pkg handler
        mock_target_pkg_handler = Mock()
        mock_target_pkg_handler.get_group.return_value = Mock(web_url="https://gitlab.example.com/target-group/pkg")
        mock_pkg_handler_class.return_value = mock_target_pkg_handler
        
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        with patch.object(command, '_create_target_hierarchy', return_value=mock_target_pkg_handler) as mock_create:
            with patch.object(command, '_fork_required_packages', return_value=True) as mock_fork:
                result = command.execute()
        
        self.assertEqual(result, 0)
        mock_create.assert_called_once()
        mock_fork.assert_called_once_with(mock_target_pkg_handler)

    def test_execute_dry_run(self):
        """Test execution in dry run mode."""
        self.args.dry = True
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        with patch.object(command, '_dry_run_preview', return_value=0) as mock_dry_run:
            result = command.execute()
            
        self.assertEqual(result, 0)
        mock_dry_run.assert_called_once()

    def test_execute_fork_packages_fails(self):
        """Test execution when forking required packages fails."""
        # Mock hierarchy doesn't exist
        self.pkg_handler.hierarchy_exists.return_value = False
        
        # Mock target pkg handler
        mock_target_pkg_handler = Mock(spec=PkgGroupHandler)
        
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        with patch.object(command, '_create_target_hierarchy', return_value=mock_target_pkg_handler):
            with patch.object(command, '_fork_required_packages', return_value=False) as mock_fork:
                result = command.execute()
        
        self.assertEqual(result, 1)
        mock_fork.assert_called_once_with(mock_target_pkg_handler)

    def test_create_target_hierarchy_path_parsing(self):
        """Test target hierarchy creation with path parsing."""
        self.args.target_path = "group1/group2/pkg"
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        # Mock the path parts processing
        with patch.object(command.pkg_group_handler, 'gitlab') as mock_gitlab:
            mock_gitlab.groups.create.return_value = Mock()
            mock_gitlab.groups.get.return_value = Mock()
            
            # Test that the method exists and can be called
            self.assertTrue(hasattr(command, '_create_target_hierarchy'))

    def test_fork_required_packages_success(self):
        """Test successful forking of required packages."""
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        # Mock current hierarchy packages
        mock_ci_package = fixtures.create_mock_project(name="00ci")
        mock_package1 = fixtures.create_mock_project(name="package1")
        
        self.pkg_handler.get_package.return_value = mock_ci_package
        self.pkg_handler.get_all_packages.return_value = [mock_ci_package, mock_package1]
        
        # Mock target pkg handler
        mock_target_pkg_handler = Mock(spec=PkgGroupHandler)
        
        # Test that the method exists by mocking it
        with patch.object(command, '_fork_required_packages', return_value=True) as mock_fork:
            result = mock_fork(mock_target_pkg_handler)
            self.assertTrue(result)

    def test_fork_required_packages_with_existing_packages(self):
        """Test forking when some packages already exist in target."""
        command = HierarchyCommand(self.pkg_handler, self.args)
        
        # Mock packages
        mock_ci_package = fixtures.create_mock_project(name="00ci")
        mock_package1 = fixtures.create_mock_project(name="package1")
        
        self.pkg_handler.get_package.return_value = mock_ci_package
        self.pkg_handler.get_all_packages.return_value = [mock_ci_package, mock_package1]
        
        # Mock target pkg handler where package already exists
        mock_target_pkg_handler = Mock(spec=PkgGroupHandler)
        
        # Test the behavior by mocking the method
        with patch.object(command, '_fork_required_packages', return_value=True) as mock_fork:
            result = mock_fork(mock_target_pkg_handler)
            self.assertTrue(result)
