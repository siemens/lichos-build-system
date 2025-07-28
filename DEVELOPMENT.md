# lichoscli Development Guide

This document contains information for developers working on lichoscli itself.

## Project Structure

```
lichoscli/
├── lichoscli/              # Main package
│   ├── __main__.py         # CLI entry point
│   ├── cli.py              # Command line interface setup
│   ├── client.py           # GitLab API client
│   ├── pkg.py              # Package handling
│   ├── utils.py            # Common utilities
│   └── commands/           # All CLI commands
│       ├── base.py         # Base classes and command registry
│       └── *.py            # Individual command implementations
├── tests/                  # Test suite
│   ├── commands/           # Unit tests for commands
│   └── *.py                # Other test modules
├── pyproject.toml          # Project configuration
├── README.md               # User documentation
└── DEVELOPMENT.md          # This file (developer documentation)
```

## Adding New Commands

Want to add a new command? Here's how:

1. **Create the command file** in `lichoscli/commands/` (e.g., `mycommand.py`)

2. **Write your command class**:
```python
from lichoscli.commands.base import Command

class MyCommand(Command):
    """Brief description of what your command does"""

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--option", help="describe your option")
        
    def execute(self):
        # Your command logic here
        # Access arguments: self.args.option
        # Access package handler: self.pkg_group_handler
        
        return 0  # 0 = success, non-zero = error
```

3. **That's it!** The command gets automatically discovered and registered. Just make sure your class name ends with `Command`.

4. **Add tests** in `tests/commands/test_mycommand.py`

### How Auto-Discovery Works

The CLI automatically finds and loads commands by:
- Scanning all `.py` files in `lichoscli/commands/`
- Importing modules and looking for classes ending with `Command`
- Skipping files starting with `_` or `test_`
- Registering found commands for use

No need to manually update import lists anywhere!

## Testing

Run tests with:
```bash
pytest
```

Run the full test suite that exercises all commands:
```bash
./test-all-commands.sh
```

## Building and Packaging

The project uses setuptools and pyproject.toml for packaging. To build:

```bash
pip install build
python -m build
```

## Code Style

- Follow PEP 8
- Use type hints where appropriate
- Add docstrings to public functions and classes
- Keep functions focused and testable

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests for new functionality
4. Run the test suite
5. Submit a merge request
