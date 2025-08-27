import argparse
import logging
from abc import ABC, abstractmethod
from typing import Dict, Type
from gitlab import GitlabError
from lichoscli.pkg import PkgGroupHandler

logger = logging.getLogger(__name__)


class Command(ABC):

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        self.pkg_group_handler = pkg_group_handler
        self.args = args

    def validate_args(self) -> None:
        """Validate command-specific arguments. Override in subclasses if needed."""
        return

    @abstractmethod
    def execute(self) -> int:
        pass


class CommandRegister:
    _commands: Dict[str, Type["Command"]] = {}

    @classmethod
    def get_command(cls, command_name: str) -> Command:
        return cls._commands.get(command_name)

    @classmethod
    def register_all_parsers(cls, subparsers: argparse._SubParsersAction):
        for name, cls in cls._commands.items():
            sp = subparsers.add_parser(
                name, help=cls.__doc__.splitlines()[0] if cls.__doc__ else ""
            )
            func = getattr(cls, "add_arguments", None)
            if func:
                func(sp)


class CommandExecutor:

    def __init__(self, pkg_group_handler, args):
        self.pkg_group_handler = pkg_group_handler
        self.args = args

    def execute(self, command) -> int:
        if not command:
            raise ValueError("No command specified")

        command_class = CommandRegister.get_command(command.command)
        if not command_class:
            raise ValueError(f"Unknown command: {command}")

        command_instance = command_class(self.pkg_group_handler, self.args)

        command_instance.validate_args()
        try:
            return command_instance.execute()
        except GitlabError as e:
            logger.error("GitLab API error occurred: %s", e)
            return 1

