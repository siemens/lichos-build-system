from datetime import datetime
import logging
import os
import random
import re
import subprocess
import tempfile
from typing import Optional
from urllib.parse import urlparse
from tabulate import tabulate
import git
from git import InvalidGitRepositoryError
from git.repo import Repo
from git.exc import GitCommandError, NoSuchPathError
from collections import namedtuple


logger = logging.getLogger(__name__)

CI_PKG = "00ci"
CI_DEFAULT_PIPELINE_NAME = "gbp"
CI_TEMPLATE = "{name}.yml@{group}/{pkg}"
PKG_GROUP_NAME = "pkg"

class GitUtils:
    """Handle Git repository operations and parsing"""

    @staticmethod
    def get_branch(repo: Optional[Repo] = None) -> str:
        try:
            if repo is None:
                repo = Repo(".")
            branch = repo.active_branch.name
            logger.debug("Found active branch: %s", branch)
            return branch
        except Exception as e:
            logger.error("Failed to get branch name: %s", str(e))
            return ""

    @staticmethod
    def parse_repo_data(repo: Optional[Repo] = None) -> tuple[str, str, str, str] | None:
        if repo is None and os.path.exists('.git/config'):
            try:
                repo = Repo(".")
            except GitCommandError:
                pass
        if repo is None:
            return None
        url = repo.remotes.origin.url

        # Try SSH URL first
        match = re.match(
            r"git@(?P<host>[^:]+):(?P<group>.*)/(?P<package>[^/]+?)(\.git)?$", url
        )
        if match is None:
            # Try HTTP(S) URL
            match = re.match(
                r"https?://(?P<host>[^/]+)/(?P<group>.+)/(?P<package>[^/]+?)(\.git)?$", url
            )

        if match:
            r = (match.group("host"), match.group("group"), match.group("package"), repo.active_branch.name)
            logger.debug("Found host %s, group %s, package %s, branch %s", *r)
            return r

        logger.debug("Failed to parse %s", format(url))
        return None

    @staticmethod
    def get_host(repo: Optional[Repo] = None) -> str:
        try:
            t = GitUtils.parse_repo_data(repo)
            return t[0] if t else ''
        except Exception as e:
            logger.error("Failed to parse repo data: %s", str(e))
            return ""

    @staticmethod
    def get_group(repo: Optional[Repo] = None) -> str:
        repo = repo or GitUtils.get_git_repo()
        t = GitUtils.parse_repo_data(repo)
        return t[1] if t else ''

    @staticmethod
    def get_package_name_from_git_repo(repo: Optional[Repo] = None) -> str:
        try:
            t = GitUtils.parse_repo_data(repo)
            return t[2] if t else ''
        except Exception as e:
            logger.error("Failed to parse repo data: %s", str(e))
            return ""

    @staticmethod
    def get_git_repo(path: str = ".") -> Optional[Repo]:
        """Get git repository object, return None if invalid"""
        try:
            return Repo(path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            logger.error("Invalid git repository at path: %s", path)
            return None

    @staticmethod
    def get_main_group(input_group) -> str:
        index = input_group.find(PKG_GROUP_NAME)
        if index != -1:
            return input_group[:index + len(PKG_GROUP_NAME)]
        else:
            logger.warning("Group '%s' does not contain '%s', using full group path", input_group, PKG_GROUP_NAME)
            return input_group

    @staticmethod
    def delete_main_from_branch_name(branch_name):
        if branch_name.endswith("/main"):
            return branch_name[: branch_name.rfind("/")] + "/*"
        return branch_name

    @staticmethod
    def get_ref_slug(branch):
        return re.sub(r"[^a-z0-9]", "-", branch.lower()).strip("-")[:63]

    @staticmethod
    def auto_detect_git_repo(package_name: Optional[str] = None) -> Optional[Repo]:
        if package_name:
            if os.path.exists(package_name):
                return GitUtils.get_git_repo(package_name)
            
        repo = None
        d = None
        if os.path.exists(".git/config"):
            d = '.'
        else:
            for f in os.scandir():
                if f.is_dir() and os.path.exists(os.path.join(f.path, ".git/config")):
                    d = f.path
                    break

        if d:
            repo = Repo(d)

        return repo

    @staticmethod
    def has_submodules(repo: Optional[Repo] = None) -> bool:
        """Check if the repository has submodules"""
        if repo is None:
            repo = GitUtils.get_git_repo()
        
        if repo is None:
            return False
            
        try:
            gitmodules_path = os.path.join(repo.working_dir, '.gitmodules')
            return os.path.exists(gitmodules_path)
        except Exception as e:
            logger.debug("Failed to check for submodules: %s", str(e))
            return False

    @staticmethod
    def initialize_submodules(repo: Optional[Repo] = None) -> bool:
        """Initialize and update submodules if they exist"""
        if repo is None:
            repo = GitUtils.get_git_repo()
        
        if repo is None:
            logger.error("No valid git repository found")
            return False
            
        if not GitUtils.has_submodules(repo):
            logger.debug("No submodules found in repository")
            return True
            
        try:
            logger.info("Initializing and updating submodules...")
            
            repo.git.submodule('init')
            
            repo.git.submodule('update', '--recursive')
            
            logger.info("Submodules initialized and updated successfully")
            return True
            
        except GitCommandError as e:
            logger.error("Failed to initialize submodules: %s", str(e))
            return False


class CIConfigUtils:
    """Handle CI/CD configuration and pipeline operations"""

    @staticmethod
    def parse_ci_config_path(path):
        P = namedtuple('P', ['name', 'group', 'pkg', 'branch'])
        r = re.match(r'(?P<name>[^@]+).yml(?:@(?P<group>[^:]*)/(?P<pkg>[^/:]+)(?::(?P<branch>.*))?)?$', path)
        if r is None:
            return None

        return P(r.group("name"), r.group("group"), r.group('pkg'), r.group('branch'))


    @staticmethod
    def get_ci_path(group_rpath, ci_typ=CI_DEFAULT_PIPELINE_NAME, branch=None):
        ci = CI_TEMPLATE.format(name=ci_typ, group=group_rpath, pkg=CI_PKG)
        if branch:
            ci += ":" + branch
        return ci



class BuildUtils:

    @staticmethod
    def normalize_architecture(arch: str) -> str:
        """Normalize architecture name using the arch map."""
        arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
        return arch_map.get(arch, arch)


    @staticmethod
    def get_package_name(package_name_arg: str):
        if not package_name_arg or package_name_arg == "." or package_name_arg == "":
            return GitUtils.get_package_name_from_git_repo()
        return package_name_arg

    @staticmethod
    def get_branch_name(branch_name_arg: str) -> str:
        """
        Get branch name from argument or current git branch.
        If argument is empty, return current branch name.
        """
        if not branch_name_arg or branch_name_arg == ".":
            return GitUtils.get_branch()
        return branch_name_arg

    @staticmethod
    def pull_docker_image(image: str) -> int:
        """Pull Docker image and return success status"""
        logger.info("Updating %s", image)
        try:
            response = subprocess.run(("docker", "pull", image), check=False)
            return response.returncode
        except Exception as e:
            logger.error("Failed to pull Docker image %s: %s", image, e)
            return 1

    @staticmethod
    def create_tmp_env_file(env):
        env_file = tempfile.NamedTemporaryFile(
            prefix=".gitlab_env.", dir=".", mode="w", delete=False
        )
        for key in env:
            logger.debug("%s=%s", key, env[key])
            env_file.write("{0}={1}\n".format(key, env[key]))
        env_file.close()
        return env_file

    @staticmethod
    def print_build_info(script):
        print("**************************************************")
        print("********* RUN THIS TO BUILD THE PACKAGE **********")
        print("**************************************************")
        print(script)
        print("**************************************************")
        print("**************************************************")

    @staticmethod
    def build_script_command(repo_setup_cmd: str, build_cmd: str) -> str:
        """Build the script command string"""
        return f"{repo_setup_cmd} ; {build_cmd}"

    @staticmethod
    def expand_var(env):
        for key, value in env.items():
            if value is None:  # skip protected variables
                continue
            env[key] = re.sub(
                r"\${([A-Z_][A-Z0-9_]*)}", lambda m: env.get(m.group(1), ""), value
            )
        return env

    @staticmethod
    def update_environment_from_file(env, tmpdir):
        try:
            with open(
                os.path.join(tmpdir.name, "variables.env"), "r", encoding="utf-8"
            ) as f:
                variables = f.read()
                env |= dict(
                    line.split("=", 1) for line in variables.splitlines() if "=" in line
                )
        finally:
            tmpdir.cleanup()
        return env


class TimeUtils:
    """Handle time and date formatting operations"""

    @staticmethod
    def format_time_range(started=None, finished=None):
        if not started:
            return "-"

        started_dt = datetime.fromisoformat(started)

        if finished:
            finished_dt = datetime.fromisoformat(finished)
            duration = int((finished_dt - started_dt).total_seconds())
            return f"{started_dt:%Y-%m-%d %H:%M:%S} - {duration}s"
        else:
            return f"{started_dt:%Y-%m-%d %H:%M:%S}"
