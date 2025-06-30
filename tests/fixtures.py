"""
Additional test fixtures and data
"""

from unittest.mock import Mock, patch, mock_open, MagicMock
from lichoscli.pkg import PkgGroupHandler
from tests.mocks import MockGitLab, MockGitLabGroup, MockGitLabProject
import pytest
import git


class TestConstants:
    """Test constants and configuration"""

    DEFAULT_GROUP_PATH = "test-group/pkg"
    DEFAULT_PROJECT_NAME = "test-package"
    DEFAULT_BRANCH = "main"
    DEFAULT_CI_CONFIG = ".gitlab-ci.yml"

    GROUP_ID = 456
    PROJECT_ID = 123
    PIPELINE_ID = 789

    SAMPLE_PROJECTS = ["package-alpha", "package-beta", "package-gamma"]


def create_mock_args(group_rpath="test-group/pkg", **kwargs) -> Mock:
    args = Mock()
    args.project = kwargs.get("project", group_rpath)
    args.package = kwargs.get("package", "test-package")
    args.branch = kwargs.get("branch", "main")
    args.dry = kwargs.get("dry", False)
    args.debug = kwargs.get("debug", False)
    args.verbose = kwargs.get("verbose", False)
    args.host = kwargs.get("host", "gitlab.example.com")
    args.dump = kwargs.get("dump", False)
    args.command = kwargs.get("command", "test")
    for key, value in kwargs.items():
        if hasattr(args, key):
            setattr(args, key, value)
    return args


def create_mock_project(**kwargs):
    project = MockGitLabProject()
    project.id = kwargs.get("id", 123)
    project.name = kwargs.get("name", "test-package")
    project.ci_config_path = kwargs.get("ci_config_path", ".gitlab-ci.yml")
    project.builds_access_level = kwargs.get("builds_access_level", "enabled")
    project.default_branch = kwargs.get("default_branch", "main")
    project.namespace = kwargs.get("namespace", {"id": 456, "full_path": "test-group/pkg"})
    return project


def create_mock_gitlab(**kwargs):
    mock_gitlab = MockGitLab()
    mock_projects = [
        MockGitLabProject(name="package1", id=1),
        MockGitLabProject(name="package2", id=2, builds_access_level="disabled"),
        MockGitLabProject(name="package3", id=3, default_branch="develop"),
    ]
    group_rpath = "test-group/pkg"
    subproject = MockGitLabProject(name="package4", id=4, namespace={"full_path": "test-group/pkg/subgroup", "path": "subgroup"})
    mock_subgroup = MockGitLabGroup(projects=[subproject], id=789)
    mock_group = MockGitLabGroup(projects=mock_projects, subgroups=[mock_subgroup]) 

    mock_gitlab.add_group(group_rpath, mock_group)
    mock_gitlab.add_group("test-group/pkg/subgroup", mock_subgroup)

    mock_gitlab.groups.get.side_effect = lambda group_rpath_or_id: {
        "test-group/pkg": mock_group,
        "test-group/pkg/subgroup": mock_subgroup,
        456: mock_group, 
        789: mock_subgroup,
    }.get(group_rpath_or_id, None)

    # Register projects
    for project in mock_projects + [subproject]:
        mock_gitlab.add_project(project.id, project)

    return mock_gitlab

def create_mock_pipeline(**kwargs):
    pipeline = Mock()
    pipeline.id = kwargs.get("id", 789)
    pipeline.status = kwargs.get("status", "success")
    pipeline.ref = kwargs.get("ref", "main")
    pipeline.created_at = kwargs.get("created_at", "2023-01-01T00:00:00Z")
    return pipeline


def create_mock_pkg_handler(
    group_rpath="test-group/pkg", mock_gitlab: MockGitLab = create_mock_gitlab()
) -> PkgGroupHandler:
    return PkgGroupHandler(group_rpath, mock_gitlab)


def create_full_mock_pkg_handler(subgroup=None) -> PkgGroupHandler:
    mock_handler = Mock(spec=PkgGroupHandler)
    mock_handler.group_rpath = "test-group/pkg"
    if subgroup is not None:
        mock_handler.subgroup = subgroup
    return mock_handler


def create_mock_git_repo(**kwargs):
    """
    Create a parametrizable mock of git.Repo.

    Parameters (all optional):
        - remote_url: str (default: 'git@gitlab.com:your-group/platform-os/pkg/test_sub/example.git')
        - branch_name: str (default: 'main')

    Returns:
        Mock git.Repo object with the specified attributes.
    """
    remote_url = kwargs.get("remote_url", "git@gitlab.com:your-group/platform-os/pkg/test_sub/example.git")
    branch_name = kwargs.get("branch_name", "main")

    repo = Mock()

    origin = Mock()
    origin.url = remote_url
    repo.remotes = Mock()
    repo.remotes.origin = origin

    branch = Mock()
    branch.name = branch_name
    repo.active_branch = branch

    return repo


def create_mock_job(**kwargs):
    job = Mock()
    job.id = kwargs.get("id", 123)
    job.status = kwargs.get("status", "pending")
    job.name = kwargs.get("name", "test-job")
    job.ref = kwargs.get("ref", "main")
    job.created_at = kwargs.get("created_at", "2023-01-01T00:00:00Z")
    job.project_id = kwargs.get("project_id", 456)
    return job


def create_mock_author(name="Test Author", email="test@example.com"):
    author = Mock()
    author.name = name
    author.email = email
    return author


@pytest.fixture
def mock_exists():
    with patch("os.path.exists") as m:
        yield m


@pytest.fixture
def mock_file():
    with patch("builtins.open", new_callable=mock_open) as m:
        yield m


@pytest.fixture
def mock_yaml():
    with patch("yaml.safe_load") as m:
        yield m


@pytest.fixture
def mock_gitlab():
    with patch("gitlab.Gitlab") as m:
        yield m


@pytest.fixture
def magic_mock():
    return MagicMock()


@pytest.fixture
def sample_config():
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


@pytest.fixture(autouse=True)
def mock_git_repo(monkeypatch):
    """
    Mock git.Repo automatically for all tests to prevent InvalidGitRepositoryError
    This fixture runs automatically for all tests.
    """
    mock_repo = create_mock_git_repo()

    def mock_repo_constructor(*args, **kwargs):
        return mock_repo

    # Add clone_from static method to our mock constructor
    mock_repo_constructor.clone_from = Mock(return_value=mock_repo)

    monkeypatch.setattr(git, "Repo", mock_repo_constructor)
    yield mock_repo
