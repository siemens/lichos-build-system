# Project Guidelines


## Architecture

- we define abstract classes that represent interfaces a provider must implement in core folder. 
- provider classes are concret classes and must wrap provider specific implementation in a smart way that keeps the interfaces generic and the implementation hidden behind it. 
- `lichoscli/commands/*.py` are auto-discovered from `lichoscli/commands/__init__.py`; the file name becomes the subcommand name and the command class must end with `Command`.
- Keep command modules focused on argument handling and orchestration. Put business logic in `lichoscli/core/services` and provider-specific behavior in `lichoscli/providers`.
- Resolve shared services through `di_container.obtain_ref(...)` instead of constructing service implementations directly inside commands.
- Preserve the UI abstraction in `lichoscli/ui/interfaces.py`: command code should use `self.output`, `self.prompts`, and `self.console` rather than direct `print()` calls or backend-specific prompt/rendering imports.
- lichoscli is debian/trixi first tool. we only accept dependencies packaged in debian. to run locally for testing poetry might be used though
## Conventions

- Add command-specific CLI options in `add_arguments` and use `validate_args` for command-specific validation.
- Keep config resolution flowing through `lichoscli/core/config.py`; do not bypass argument, environment, repository, and default precedence with hardcoded values.
- Extend the existing pytest fixtures and mocks under `tests/fixtures` and `tests/mocks` instead of introducing ad hoc setup patterns.
- In GitLab-heavy flows such as workspace or dependency operations, reuse cached branch and group lookups when possible rather than adding repeated API calls for the same branch or group.