# Contributing to lichoscli

Thank you for helping improve `lichoscli`. Contributions are welcome through
issues and pull requests on
[github.com/siemens/lichoscli](https://github.com/siemens/lichoscli).

## Maintainers

- Sami Alzein <sami.alzein@siemens.com>
- Ludwig Nussel <ludwig.nussel@siemens.com>

The maintainers review pull requests and decide on larger design changes.
Contact them directly for questions that do not fit an issue.

## Before you start

1. Check existing issues and pull requests before starting substantial work.
2. Open an issue for a large feature or behavior change so the approach can be
   discussed first.
3. Keep changes focused and add or update tests for changed behavior.

## Development setup

Install your checkout with [pipx](https://pipx.pypa.io/) in editable mode, so
source changes take effect immediately, and add pytest to the same
environment:

```bash
pipx install --editable .
pipx inject --include-apps lichoscli pytest
```

`--include-apps` puts `pytest` on your `PATH`; it runs inside the lichoscli
environment, so it sees the installed package and its dependencies.

lichoscli requires Python 3.10 or newer. Runtime dependencies should remain
available as packages of common Linux distributions, so that those
distributions can package lichoscli itself.

## Making changes

Commands are discovered from `lichoscli/commands/`. Add a command module with a
class whose name ends in `Command`, define command-specific arguments in
`add_arguments`, and put business logic in core services or providers rather
than in the command class. Add tests alongside the relevant existing test
group.

Keep provider-specific behavior behind the abstractions in `lichoscli/core`.
Commands and core services do not import provider implementations directly.

## Tests

Run the unit test suite:

```bash
pytest
```

## Pull requests

Use a focused title and describe the user-visible behavior, compatibility
impact, and verification performed. Pull requests should include tests for
new behavior and documentation updates when a command or workflow changes.
Please respond to review feedback and keep the branch up to date with the
default branch.

Write commit subjects as [Conventional Commits](https://www.conventionalcommits.org/)
(`feat: …`, `fix: …`, `docs: …`).

## License

By contributing, you agree that your contribution is provided under the
project's [MIT License](LICENSE), unless a different license is explicitly
agreed for the contribution.
