# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import argparse
import logging
from abc import ABC, abstractmethod

from lichoscli.core.di import DIContainer
from lichoscli.core.exceptions import ProviderAPIError
from lichoscli.ui import UserInterface

logger = logging.getLogger(__name__)


class Command(ABC):

    def __init__(self, di_container: DIContainer, args):
        self.di_container = di_container
        self.args = args
        self.ui = self.di_container.obtain_ref(UserInterface)
        self.output = self.ui.output
        self.prompts = self.ui.prompts
        self.console = self.output.console

    def validate_args(self) -> None:
        """Validate command-specific arguments. Override in subclasses if needed."""
        return

    @abstractmethod
    def execute(self) -> int:
        pass


class CommandRegister:
    _commands: dict[str, type["Command"]] = {}

    @classmethod
    def get_command(cls, command_name: str) -> Command:
        return cls._commands.get(command_name)

    @classmethod
    def register_all_parsers(cls, subparsers: argparse._SubParsersAction):
        for name, cls in cls._commands.items():
            sp = subparsers.add_parser(name, help=cls.__doc__.splitlines()[0] if cls.__doc__ else "")
            func = getattr(cls, "add_arguments", None)
            if func:
                func(sp)


class CommandExecutor:

    def __init__(self, di_container: DIContainer, args):
        self.di_container = di_container
        self.args = args

    def execute(self, command) -> int:
        if not command:
            raise ValueError("No command specified")

        command_class = CommandRegister.get_command(command.command)
        if not command_class:
            raise ValueError(f"Unknown command: {command}")

        command_instance = command_class(self.di_container, self.args)

        command_instance.validate_args()
        try:
            return command_instance.execute()
        except ProviderAPIError as e:
            logger.error("Provider API error: %s", e)
            return 1
