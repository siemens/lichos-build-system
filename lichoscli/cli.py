#!/usr/bin/python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG
import argparse
import logging
import sys

import argcomplete

from lichoscli.commands.base import CommandExecutor, CommandRegister
from lichoscli.completers import attach_completers
from lichoscli.core.config import ConfigBuilder
from lichoscli.core.container_factory import DIContainerFactory

logger = logging.getLogger(__name__)


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
        help="main group path for the distribution (resolved from .lichos anchor if omitted)",
    )
    parser.add_argument(
        "--branch",
        help="branch name for some commands",
    )
    parser.add_argument("--dump", action="store_true", help="some command allow dumping json data")
    parser.add_argument(
        "--output-backend",
        dest="output_backend",
        choices=["terminal"],
        help="output rendering backend (default: terminal, env: LICHOS_OUTPUT_BACKEND)",
    )
    parser.add_argument(
        "--prompt-backend",
        dest="prompt_backend",
        choices=["terminal"],
        help="interactive prompt backend (default: terminal, env: LICHOS_PROMPT_BACKEND)",
    )

    subparsers = parser.add_subparsers(dest="command", title="Commands")

    CommandRegister.register_all_parsers(subparsers)

    attach_completers(parser)
    argcomplete.autocomplete(parser)

    args = parser.parse_args()

    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(1)

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

    try:
        command_class = CommandRegister.get_command(args.command)
        if command_class:
            command_class.prepare_args(args)

        config_builder = ConfigBuilder(args)
        config = config_builder.build()
        logger.debug("Configuration: host=%s, pkg_group=%s, branch=%s, provider=%s",
                     config.host, config.pkg_group, config.branch, config.provider)
        
        args.branch_explicitly_provided = config.branch_explicitly_provided
        args.branch = config.branch
        logger.debug("Using branch: %s (explicitly provided: %s)",
                     args.branch, args.branch_explicitly_provided)
        di_container = DIContainerFactory.create(config)
        
        executor = CommandExecutor(di_container, args)
        result = executor.execute(args)
        return 0 if result is None else result

    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user.")
        return 130
    except ValueError as e:
        logger.error(str(e))
        return 1
    except (argparse.ArgumentError, RuntimeError) as e:
        logger.error("Error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
