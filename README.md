# lichoscli - git hosting platform CLI tool for Linux package and distro development

lichoscli coordinates distribution development using a general purpose set of tools like a git hosting platform
with CI, a container runtime and a package repository. A team that already
operates these services can reuse them for package builds and multi-package
changes. It integrates all of that to provide a distribution-relevant view in one place.

| Distribution need | Provided by | Supported today |
|---|---|---|
| Package sources, review, permissions | Git hosting platform | GitLab |
| Build farm and build logs | The platform's CI | GitLab CI |
| Build environment, locally and in CI | Container runtime | Docker, Podman |
| Binary archive and snapshots | Package repository | Any apt repository |

Each package lives in its own repository with its own history, permissions,
merge requests and pipeline. lichoscli turns that set of repositories into one
distribution.

The name originates from a Siemens internal, Debian-based operating system for electric-vehicle chargers (hence LiChOS - Linux Charger Operating System).

## Installation

lichoscli needs Python 3.10 or newer and Git, and installs with
[pipx](https://pipx.pypa.io/). [INSTALL.md](INSTALL.md) covers installing it
and setting up shell completion.

## Quick start

After running `lichoscli setup` list the packages of a distribution:

```console
$ lichoscli --host salsa.debian.org --pkg-group systemd-team list
Packages
  Name               Type                 Enabled  Branch
  -----------------  -------------------  -------  -------------
  casync             debian/salsa-ci.yml  enabled  master
  mkosi              debian/salsa-ci.yml  enabled  debian/sid
  python-systemd     local                enabled  master
  systemd            debian/salsa-ci.yml  enabled  debian/master
  systemd-bootchart  debian/salsa-ci.yml  enabled  master
  systemd-cron       debian/salsa-ci.yml  enabled  master
  systemd-netlogd    debian/salsa-ci.yml  enabled  debian/latest
  systemd-udeb       debian/salsa-ci.yml  enabled  debian/sid
```

Clone a package and inspect its latest pipeline:

```console
$ lichoscli clone https://salsa.debian.org/systemd-team/mkosi
$ cd systemd-team/mkosi
$ lichoscli status .
Pipeline Details - mkosi
  Setting  Value
  -------  --------------------------------------------------------------
  sha      3ff85dba93552d06848caeb61b98747a874cf31c
  ref      master
  status   failed
  source   push
  web_url  https://salsa.debian.org/systemd-team/mkosi/-/pipelines/393059
Pipeline Jobs
  Id       Name                   Stage         Status   Started
  -------  ---------------------  ------------  -------  --------------------------
  2922893  piuparts               test          success  2022-06-27 13:05:36 - 160s
  2922892  blhc                   test          success  2022-06-27 13:05:35 - 73s
  2922891  autopkgtest            test          success  2022-06-27 13:05:34 - 183s
  2922890  lintian                test          success  2022-06-27 13:05:33 - 110s
  2922889  reprotest              test          failed   2022-06-27 13:05:32 - 129s
  ...
$ lichoscli log . reprotest
```

These commands work against any GitLab group of packages.

## Command reference

### Packages and CI

| Command | Purpose |
|---|---|
| `lichoscli show .` | Package settings; `--branches` lists branches |
| `lichoscli status .` | Latest pipeline and its jobs on the current branch |
| `lichoscli log . <job>` | Job log; `--wait --follow` waits for the job and streams it |
| `lichoscli trigger . [<job>]` | Start a pipeline, or retry one job of the latest pipeline |
| `lichoscli getartifacts . <job>` | Download a job's artifacts |
| `lichoscli browse .` | Open the package in a web browser |
| `lichoscli pdiff .` | Diff a forked package against its parent |
| `lichoscli enable .` / `disable .` | Turn package builds on or off |

The other commands, such as workspaces, dependency-ordered build scheduling
and releases, expect the GitLab projects and their CI to follow a specific
contract. That contract is still a work in progress, and its documentation
will be published soon.

## Maintainers

lichoscli was written and is maintained by:

- Ludwig Nussel <ludwig.nussel@siemens.com>
- Sami Alzein <sami.alzein@siemens.com>

Report bugs and propose changes through
[issues](https://github.com/siemens/lichoscli/issues); see
[CONTRIBUTING.md](CONTRIBUTING.md).
