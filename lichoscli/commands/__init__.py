# src/commands/__init__.py

import importlib
import re
from pathlib import Path
from .base import Command, CommandRegister

__all__ = ["Command", "CommandRegister"]

commands_dir = Path(__file__).parent

command_pattern = re.compile(r"^(?!_|test_).*\.py$")

for file_path in commands_dir.glob("*.py"):
    module_name = file_path.stem

    if module_name in ["__init__", "base"]:
        continue

    if command_pattern.match(file_path.name):
        module = importlib.import_module(f".{module_name}", package=__name__)

        for attr_name in dir(module):
            if attr_name.endswith("Command") and attr_name != "Command":
                cls = getattr(module, attr_name)
                globals()[attr_name] = cls
                __all__.append(attr_name)
                CommandRegister._commands[module_name] = cls
