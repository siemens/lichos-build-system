# Installation

## From Packages

If you have the lichos repos enabled, just call

```bash
apt install lichoscli
```

## Directly from git

```bash
ln -s $PWD/cli ~/bin/lichoscli
```

## Virtual environment

Install system-wide into an isolated virtual environment using [pipx](https://pipx.pypa.io/):

```bash
pipx install .
```

To reinstall after updating the source:

```bash
pipx install . --force
```

The `lichoscli` and `lbs` commands will be available in `~/.local/bin`.
