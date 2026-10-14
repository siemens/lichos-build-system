# Agent Instructions

## Architecture

- Abstract classes in `lichoscli/core` define the interfaces a provider must implement.
- Provider classes in `lichoscli/providers` are concrete implementations. They wrap provider-specific behavior so the interfaces stay generic and the implementation stays hidden behind them.
- `lichoscli/commands/*.py` are auto-discovered from `lichoscli/commands/__init__.py`; the file name becomes the subcommand name and the command class name must end with `Command`.
- Keep command modules focused on argument handling, prompting, presentation and orchestration. Put business logic in `lichoscli/core/services` and provider-specific behavior in `lichoscli/providers`.
- Resolve shared services through `di_container.obtain_ref(...)` instead of constructing service or provider implementations directly inside commands.
- Preserve the UI abstraction in `lichoscli/ui/interfaces.py`: command code uses `self.output`, `self.prompts` and `self.console`, never direct `print()` calls or backend-specific prompt/rendering imports.
- lichoscli is a Debian Trixie first tool: only add dependencies that are packaged in Debian Trixie. Poetry may be used to run it locally for testing.

## Conventions

- Add command-specific CLI options in `add_arguments` and command-specific validation in `validate_args`.
- Keep config resolution flowing through `lichoscli/core/config.py`; do not bypass the argument, environment, repository and default precedence with hardcoded values.
- Extend the existing pytest fixtures and mocks under `tests/fixtures` and `tests/mocks` instead of introducing ad hoc setup patterns.
- In GitLab-heavy flows such as workspace or dependency operations, reuse cached branch and group lookups rather than repeating API calls for the same branch or group.

## Python string formatting (all `*.py` files)

- Do not use f-strings. Use plain strings or `.format(...)` for interpolation.
- In logging calls, pass arguments to the logger for deferred interpolation instead of pre-formatting the message.
- If an existing block already uses f-strings heavily, do not mix styles within the same small expression flow; either keep the local pattern or refactor the block consistently.

## Provider-agnostic boundaries (`lichoscli/commands/`, `lichoscli/core/services/`)

- Provider agnosticism is a hard rule here: do not import from `lichoscli/providers` or provider SDKs such as `gitlab` or `github`.
- Core services depend on the generic abstractions declared in `lichoscli/core`, not on provider-specific classes or data shapes.
- If new provider-specific behavior is needed, add or extend a provider-agnostic interface in `lichoscli/core` and keep the concrete implementation in `lichoscli/providers`.
- Avoid provider-shaped data access, including raw `.attributes` dictionaries, provider-only fields or direct manager APIs. Expose the data through core models, interfaces or service methods instead.

## python-gitlab usage (`lichoscli/providers/gitlab/`)

- Before implementing a python-gitlab API call, consult the relevant section of https://python-gitlab.readthedocs.io/en/v4.9.0/index.html to confirm the correct pattern.
- Use `.get()` to fetch a single object, mutate its attributes, then call `.save()`; do not delete and recreate objects when an update is possible.
- Use manager methods (`.list()`, `.get()`, `.create()`, `.delete()`) on the appropriate manager attribute (`project.protectedbranches`, `project.branches`, ...).
- Do not rebuild a payload from an existing object's attributes to pass back into `.create()` when `.save()` is available.
- Check the docs for which managers support `SaveMixin` (`.save()`) and which are create/delete-only before choosing an update strategy.
