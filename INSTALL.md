# Installation

lichoscli needs Python 3.10 or newer and Git. Local builds also need Docker
or Podman.

## From a Git repository with pipx

Install the latest source version into an isolated environment using
[pipx](https://pipx.pypa.io/). pipx accepts any Git URL, so this works for
the upstream repository, a fork or a mirror:

```bash
pipx install git+https://github.com/siemens/lichos-build-system.git
```

Append `@<branch-or-tag>` to the URL to install a specific version.

## From a local checkout

```bash
pipx install .
```

To reinstall after updating the source:

```bash
pipx install . --force
```

The `lichoscli` and `lbs` commands will be available in the pipx environment,
normally under `~/.local/bin`.

## Shell completion

lichoscli completes commands, options and package names through
[argcomplete](https://github.com/kislyuk/argcomplete). Install argcomplete
with `pipx install argcomplete` and add this to your bash or zsh startup file:

```bash
eval "$(register-python-argcomplete lichoscli)"
eval "$(register-python-argcomplete lbs)"
```
