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
from collections import namedtuple


logger = logging.getLogger(__name__)

CI_PKG = "00ci"
CI_DEFAULT_PIPELINE_NAME = "gbp"
CI_TEMPLATE = "{name}.yml@{group}/{pkg}"
PKG_GROUP_NAME = "pkg"

class GitUtils:
    """Handle Git repository operations and parsing"""

    @staticmethod
    def get_branch(repo: git.Repo = None) -> str:
        try:
            if repo is None:
                repo = git.Repo(".")
            branch = repo.active_branch.name
            logger.debug("Found active branch: %s", branch)
            return branch
        except Exception as e:
            logger.error("Failed to get branch name: %s", str(e))
            return ""

    @staticmethod
    def parse_repo_data(repo: git.Repo = None) -> tuple[str, str, str, str] | None:
        if repo is None and os.path.exists('.git/config'):
            try:
                repo = git.Repo(".")
            except git.exc.InvalidGitRepositoryError:
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
    def get_host(repo: git.Repo = None) -> str:
        try:
            t = GitUtils.parse_repo_data(repo)
            return t[0] if t else ''
        except Exception as e:
            logger.error("Failed to parse repo data: %s", str(e))
            return ""

    @staticmethod
    def get_group(repo: git.Repo = None) -> str:
        try:
            t = GitUtils.parse_repo_data(repo)
            return t[1] if t else ''
        except Exception as e:
            logger.error("Failed to parse repo data: %s", str(e))
            return ""

    @staticmethod
    def get_package_name_from_git_repo(repo: git.Repo = None) -> str:
        try:
            t = GitUtils.parse_repo_data(repo)
            return t[2] if t else ''
        except Exception as e:
            logger.error("Failed to parse repo data: %s", str(e))
            return ""

    @staticmethod
    def get_git_repo(path: str = ".") -> Optional[git.Repo]:
        """Get git repository object, return None if invalid"""
        try:
            return git.Repo(path)
        except git.exc.InvalidGitRepositoryError:
            logger.error("Invalid git repository at path: %s", path)
            return None

    @staticmethod
    def get_main_group(input_group) -> str:
        index = input_group.find(PKG_GROUP_NAME)
        if index != -1:
            return input_group[:index + len(PKG_GROUP_NAME)]
        else:
            raise ValueError("Group '{}' is not part of a group named '{}'".format(main_group_name, input_group))

    @staticmethod
    def delete_main_from_branch_name(branch_name):
        if branch_name.endswith("/main"):
            return branch_name[: branch_name.rfind("/")] + "/*"
        return branch_name

    @staticmethod
    def get_ref_slug(branch):
        return re.sub(r"[^a-z0-9]", "-", branch.lower()).strip("-")[:63]

    @staticmethod
    def auto_detect_git_repo():
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
            repo = git.Repo(d)

        return repo

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
    def get_type_from_ci_path(ci_config_path):
        t = CIConfigUtils.parse_ci_config_path(ci_config_path)
        if t is None:
            raise ValueError("ci_config_path is not set or invalid")
        return t.name

    @staticmethod
    def get_ci_path(group_rpath, ci_typ=CI_DEFAULT_PIPELINE_NAME, branch=None):
        ci = CI_TEMPLATE.format(name=ci_typ, group=group_rpath, pkg=CI_PKG)
        if branch:
            ci += ":" + branch
        return ci

    @staticmethod
    def format_variables_table(variables: list, print_masked: bool = True) -> str:
        """Format GitLab variables into a table string"""
        headers = [
            "type",
            "key",
            "value",
            "hidden",
            "protected",
            "masked",
            "raw",
            "scope",
            "description",
        ]
        rows = [headers]

        for v in variables:
            row = [
                v.variable_type,
                v.key,
                "***" if (v.masked and print_masked) else v.value,
                v.hidden,
                v.protected,
                v.masked,
                v.raw,
                v.environment_scope,
                v.description,
            ]
            rows.append(row)

        if len(rows) > 1:
            return "GitLab CI/CD Variables:\n" + tabulate(rows, headers="firstrow")
        return ""


class BuildUtils:

    @staticmethod
    def ensure_url_scheme(url: str) -> str:
        """
        Ensure URL has a scheme (https:// if none provided).
        """
        parsed = urlparse(url)
        if not parsed.scheme:
            # If no scheme is present, add https://
            return f"https://{url}"
        return url

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
    def build_docker_command(
        env_file_path: str,
        image: str,
        ci_project_dir: str,
        platform: str,
        script: Optional[str] = None,
        shell: Optional[str] = None,
        current_dir: Optional[str] = None,
    ) -> list:
        """Build Docker run command"""
        if current_dir is None:
            current_dir = os.getcwd()

        cmd = [
            "docker",
            "run",
            "--env-file",
            env_file_path,
            "--rm",
            "-v",
            f"{current_dir}:{ci_project_dir}",
            "--platform",
            platform,
            "-w",
            ci_project_dir,
        ]

        if shell:
            cmd.extend(["-it", image, shell])
        elif script:
            cmd.extend([image, "/usr/bin/bash", "-c", script])
        else:
            raise ValueError("Either shell or script must be provided")

        logger.info("Docker command: %s", cmd)
        return cmd

    @staticmethod
    def determine_project_directory(has_shell: bool = False) -> str:
        """Determine project directory path"""
        shell_project_dir = "/build"
        if has_shell:
            return shell_project_dir
        return "/" + "".join(
            random.sample(shell_project_dir[1:], k=len(shell_project_dir[1:]))
        )

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
        print("********** RUNNING TO BUILD THE PACKAGE **********")
        print("**************************************************")
        print(script)
        print("**************************************************")
        print("**************************************************")

    @staticmethod
    def build_script_command(repo_setup_cmd: str, build_cmd: str) -> str:
        """Build the script command string"""
        return f"{repo_setup_cmd} ; {build_cmd}"

    @staticmethod
    def run_docker_build(
        docker_cmd: list, env_file_path: str, cleanup_env_file: bool = True
    ) -> int:
        """Execute Docker build command and return exit code"""
        try:
            response = subprocess.run(docker_cmd, check=False)
            return response.returncode
        finally:
            if cleanup_env_file and os.path.exists(env_file_path):
                os.unlink(env_file_path)

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

    @staticmethod
    def get_file_from_dir(artifacts_dir: str, filename: str) -> Optional[str]:
        """
        Get a specific file from the artifacts directory.
        Returns the full path to the file if found, otherwise None.
        """
        file_path = os.path.join(artifacts_dir, filename)
        if os.path.isfile(file_path):
            return file_path
        logger.warning(
            "File %s not found in artifacts directory %s", filename, artifacts_dir
        )
        return None


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
