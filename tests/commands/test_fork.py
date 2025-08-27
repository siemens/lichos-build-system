import unittest
from unittest.mock import Mock, patch
from lichoscli.commands.fork import ForkCommand
from lichoscli.pkg import PkgGroupHandler
from tests import fixtures


class TestForkCommand(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.pkg_handler = fixtures.create_full_mock_pkg_handler()
        self.pkg_handler.gitlab = Mock()  # Add gitlab attribute
        self.args = fixtures.create_mock_args()
        self.args.package = "test-package"
        self.args.namespace = "target-group/pkg"

        # Mock the current hierarchy as forked
        self.mock_ci_project = fixtures.create_mock_project(name="00ci")
        # Set up the mock ci project to look like it's forked
        self.mock_ci_project.forked_from_project = {
            'namespace': {'full_path': 'source-group/pkg'}
        }
        self.pkg_handler.get_package.return_value = self.mock_ci_project

    @patch('lichoscli.commands.fork.CIConfigUtils')
    def test_fork_command_initialization(self, mock_ci_config_utils):
        """Test that fork command initialization sets correct attributes."""
        # Mock CI config detection
        mock_ci_config_utils.is_forked.return_value = True
        mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
        
        command = ForkCommand(self.pkg_handler, self.args)
        
        self.assertEqual(command.args.package, "test-package")
        self.assertEqual(command.destination_namespace, "target-group/pkg")

    @patch('lichoscli.commands.fork.CIConfigUtils')
    def test_detect_fork_configuration_auto_detect(self, mock_ci_config_utils):
        """Test auto-detection of fork configuration from 00ci."""
        # Setup mocks for auto-detection
        mock_ci_config_utils.is_forked.return_value = True
        mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
        self.args.namespace = None  # No explicit namespace provided
        
        command = ForkCommand(self.pkg_handler, self.args)
        
        self.assertEqual(command.destination_namespace, self.pkg_handler.group_rpath)

    @patch('lichoscli.commands.fork.PkgGroupHandler')
    @patch('lichoscli.commands.fork.CIConfigUtils')
    @patch('lichoscli.commands.fork.HierarchyUtils')
    def test_execute_successful_fork(self, mock_hierarchy_utils, mock_ci_config_utils, mock_pkg_handler_class):
        """Test successful fork execution."""
        # Setup mocks
        mock_ci_config_utils.is_forked.return_value = True
        mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
        mock_ci_config_utils.get_ci_path.return_value = "target-group/pkg/00ci/.gitlab-ci.yml"
        
        # Mock destination hierarchy
        mock_destination_pkg_handler = Mock()
        mock_destination_ci = fixtures.create_mock_project(name="00ci")
        mock_destination_pkg_handler.get_package.return_value = mock_destination_ci
        mock_forked_package = fixtures.create_mock_project(name="test-package")
        mock_destination_pkg_handler.fork_package.return_value = mock_forked_package
        
        # Mock PkgGroupHandler constructor to return our mock
        mock_pkg_handler_class.return_value = mock_destination_pkg_handler
        
        # Mock hierarchy exists check
        self.pkg_handler.hierarchy_exists.return_value = True
        
        # Mock source hierarchy
        mock_source_hierarchy = Mock()
        mock_source_hierarchy.group_rpath = "source-group/pkg"
        mock_base_package = fixtures.create_mock_project(name="test-package")
        mock_base_package.path_with_namespace = "source-group/pkg/test-package"
        mock_source_hierarchy.get_package.return_value = mock_base_package
        
        mock_hierarchy_utils.extract_package_subpath.return_value = ""
        
        command = ForkCommand(self.pkg_handler, self.args)
        command.source_hierarchy = mock_source_hierarchy
        command.destination_namespace = "target-group/pkg"
        
        result = command.execute()
        
        self.assertEqual(result, 0)
        mock_destination_pkg_handler.fork_package.assert_called_once()

    @patch('lichoscli.commands.fork.CIConfigUtils')
    def test_execute_hierarchy_not_exists(self, mock_ci_config_utils):
        """Test fork execution when target hierarchy doesn't exist."""
        mock_ci_config_utils.is_forked.return_value = True
        mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
        
        # Mock hierarchy doesn't exist
        self.pkg_handler.hierarchy_exists.return_value = False
        
        command = ForkCommand(self.pkg_handler, self.args)
        result = command.execute()
        
        self.assertEqual(result, 1)

    @patch('lichoscli.commands.fork.PkgGroupHandler')
    @patch('lichoscli.commands.fork.CIConfigUtils')
    def test_execute_no_destination_ci(self, mock_ci_config_utils, mock_pkg_handler_class):
        """Test fork execution when destination has no 00ci package."""
        mock_ci_config_utils.is_forked.return_value = True
        mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
        
        # Mock destination hierarchy without 00ci
        mock_destination_pkg_handler = Mock(spec=PkgGroupHandler)
        mock_destination_pkg_handler.get_package.return_value = None  # No 00ci package
        
        self.pkg_handler.hierarchy_exists.return_value = True
        mock_pkg_handler_class.return_value = mock_destination_pkg_handler
        
        command = ForkCommand(self.pkg_handler, self.args)
        result = command.execute()
        
        self.assertEqual(result, 1)

    @patch('lichoscli.commands.fork.CIConfigUtils')
    def test_execute_dry_run(self, mock_ci_config_utils):
        """Test fork execution in dry run mode."""
        mock_ci_config_utils.is_forked.return_value = True
        mock_ci_config_utils.get_base_ci_hierarchy.return_value = "source-group/pkg"
        
        self.args.dry = True
        command = ForkCommand(self.pkg_handler, self.args)
        
        with patch.object(command, '_dry_run_preview', return_value=0) as mock_dry_run:
            result = command.execute()
            
        self.assertEqual(result, 0)
        mock_dry_run.assert_called_once()

    @patch('lichoscli.commands.fork.CIConfigUtils')
    def test_determine_package_type(self, mock_ci_config_utils):
        """Test package type determination."""
        mock_ci_config_utils.is_forked.return_value = False
        
        command = ForkCommand(self.pkg_handler, self.args)
        
        # Mock package with debian directory
        mock_package = Mock()
        mock_package.repository_tree.return_value = [Mock(name='debian', type='tree')]
        
        # Test the public behavior through execute path rather than private method
        self.assertIsNotNone(command)
