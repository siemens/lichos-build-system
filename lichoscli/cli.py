#!/usr/bin/python3
import argparse
import logging
import sys
import os
from lichoscli.providers.gitlab import GitLabClientFactory
from lichoscli.commands.base import CommandExecutor, CommandRegister
from lichoscli.pkg import PkgGroupHandler
# noqa: F403
from lichoscli.commands import *
from lichoscli.utils import GitUtils

logger = logging.getLogger(__name__)#


class CustomFormatter(logging.Formatter):
    """Custom logging formatter that uses shorter level indicators"""

    level_mapping = {
        logging.DEBUG: "[D]",
        logging.INFO: "[I]",
        logging.WARNING: "[W]",
        logging.ERROR: "[E]",
        logging.CRITICAL: "[C]",
    }

    def format(self, record):
        # Replace the levelname with our custom level indicator
        record.levelname = self.level_mapping.get(record.levelno, record.levelname)
        return super().format(record)

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="lichoscli",
        description="CLI tool to manage package builds in gitlab using the lichos framework",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument("--dry", action="store_true", help="dry run")
    parser.add_argument("--debug", action="store_true", help="debug output")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose")
    parser.add_argument("--host", help="gitlab host name")
    parser.add_argument(
        "--pkg-group",
        help="main group path that contains the 00ci project",
    )
    parser.add_argument(
        "--branch",
        help="branch name for some commands",
    )
    parser.add_argument(
        "--dump", action="store_true", help="some command allow dumping json data"
    )

    subparsers = parser.add_subparsers(dest="command", title="Commands")

    CommandRegister.register_all_parsers(subparsers)

    args = parser.parse_args()

    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(1)

    args.branch_explicitly_provided = args.branch is not None

    # Configure logging with custom formatter
    handler = logging.StreamHandler()
    formatter = CustomFormatter("%(levelname)s %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = []  # Remove any existing handlers
    root_logger.addHandler(handler)

    if args.debug:
        root_logger.setLevel(logging.DEBUG)
    elif args.verbose:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.WARNING)

    args.branch = args.branch or os.environ.get('LICHOS_BRANCH') or GitUtils.get_branch()

    if args.host is None and args.pkg_group is None:
        repo = GitUtils.auto_detect_git_repo()
        if repo:
            logger.debug("found git repo in %s", repo.working_dir)
            data = GitUtils.parse_repo_data(repo)
            if data:
                if args.host is None:
                    args.host = data[0]
                if args.pkg_group is None:
                    args.pkg_group = data[1]
                if args.branch is None:
                    args.branch = data[3]
            else:
                logger.debug("Failed to parse repo data in %s", repo.working_dir)

    if args.host is None or args.pkg_group is None:
        logger.error("Please specify host and group manually")
        return 1

    if args.branch is None:
        logger.error("Please specify branch manually or set LICHOS_BRANCH environment variable")
        return 1

    gl = GitLabClientFactory(args.host).create()


    pkg_group_handler = PkgGroupHandler(args.pkg_group, gl)

    try:
        executor = CommandExecutor(pkg_group_handler, args)
        result = executor.execute(args)
        return 0 if result is None else result

    except (argparse.ArgumentError, ValueError, RuntimeError) as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
