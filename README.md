# lichoscli - LiChOS Build System CLI

A command-line tool for managing LiChOS package builds and GitLab CI/CD pipelines. When run from within a git checkout, lichoscli automatically detects the package you're working on. You can also operate at the project level when you have the `00ci` package checked out.

## Setup

lichoscli uses the same config as [GitLab CLI](https://docs.gitlab.com/editor_extensions/gitlab_cli/) for authentication. By default it looks for `~/.config/glab-cli/config.yml` (or `~/snap/glab/current/.config/glab-cli/config.yml` for snap installs).

Minimal config example:
```yaml
hosts:
    gitlab.example.com:
        token: <token>
        api_host: gitlab.example.com
        git_protocol: https
        api_protocol: https
        user: <username>
```

## Quick Start

**Choose presentation backends when needed:**
```bash
# Stdlib-only raw output instead of styled Rich tables
lichoscli --output-backend raw list

# Raw prompts and raw output together
lichoscli --output-backend raw --prompt-backend raw workspace enter

# Use questionary prompts if the optional extra is installed
pip install 'lichoscli[questionary]'
lichoscli --prompt-backend questionary workspace enter
```

The CLI now separates rendering from command logic:
- `--output-backend rich|raw` controls output rendering.
- `--prompt-backend prompt-toolkit|questionary|raw` controls interactive selection and confirmation prompts.

This lets command modules stay focused on orchestration while presentation backends can be swapped independently.

**Get started with a project:**
```bash
# Clone the 00ci package to set up project detection
lichoscli --host gitlab.example.com --pkg-group your-group/platform-os/pkg --branch main clone 00ci
```

**List packages:**
```bash
# Current project
lichoscli list

# Different project
lichoscli --pkg-group your-group/platform-os/pkg --host gitlab.example.com list
```

## Common Workflows

### Working with Packages

**Clone a package:**
```bash
lichoscli clone u-boot
```

> **Pro tip:** lichoscli automatically sets up useful remotes when cloning. If it's a fork, you get a `parent` remote for the `pdiff` command. If there's a `Repository` in `debian/upstream/metadata`, that becomes the `upstream` remote.

Now the there's a local git checkout of the specified package. You
can enter the directory and execute lichoscli commands from there.
When in such a local git checkout, it's possible to specify `.` as
package name to refer to the currently checkout one one.

Also, lichoscli will operate on the checked out branch by default
unless entering a workspace. See below.

**See package configuration:**
```bash
$ lichoscli show lichoscli
   Package Information: lichoscli
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Setting              ┃ Value     ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ id                   │ 438106    │
│ path                 │ lichoscli │
│ builds_access_level  │ enabled   │
│ ci_config_path       │ gbp       │
│ default_branch       │ flocken   │
└──────────────────────┴───────────┘
```

**Enter a namespace (ie work on branch):**
```bash
$ lichoscli workspace enter flocken
```

> **Pro tip:** Entering a workspace exports the environment variable `LICHOS_BRANCH`. You can add that to your `$PS1` to have a visual hint that the current shell is in a lichos workspace

Now all commands operate on the given branch by default

**Check pipeline status:**
```bash
$ lichoscli status .
                                    Pipeline Details - lichoscli
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Setting ┃ Value                                                                                  ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ sha     │ 8f243038e5f017a22108e9505191f8371069dddb                                               │
│ ref     │ flocken                                                                                │
│ status  │ success                                                                                │
│ source  │ api                                                                                    │
│ web_url │ https://github.com/samastek/lichoscli/actions/runs/55019024 │
└─────────┴────────────────────────────────────────────────────────────────────────────────────────┘
                               Pipeline Jobs
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Id        ┃ Name          ┃ Stage  ┃ Status  ┃ Started                   ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 320264317 │ publish       │ deploy │ success │ 2025-11-21 11:37:59 - 19s │
│ 320264316 │ build-amd64   │ build  │ success │ 2025-11-21 11:36:27 - 80s │
│ 320264315 │ build-arm64   │ build  │ success │ 2025-11-21 11:36:55 - 52s │
│ 320264314 │ calculate-env │ .pre   │ success │ 2025-11-21 11:35:45 - 29s │
└───────────┴───────────────┴────────┴─────────┴───────────────────────────┘
```

**View job logs:**
```bash
$ lichoscli log . build-amd64
[...]
```

To view the live log and wait for a job to start (e.g. after a
recent push or trigger)
```bash
$ lichoscli log --wait --follow build-amd64
```

**Trigger a pipeline:**
```bash
$ cd lichoscli
$ lichoscli trigger .
```

### Local Development

Local package builds are performed inside a docker container that is
pulled from the gitlab project you are working against. You may need
to configure docker authentication to be able to build images from
there.

**Build packages locally:**
```bash
lichoscli build
```

**Open a shell in the build environment:**
```bash
lichoscli build --shell
```

sometimes if you are behind zscalar, you need to use ipv4net form docker for that 
```bash
lichoscli build . --shell --architecture arm64 --network <ip4 network name>
```

Specify custom shell (use --shell= if followed by other options)
```bash
lichoscli build . --shell=/bin/zsh
```

> **Note:** Local builds are somewhat limited and expect specific pipeline layouts. The shell option prints a script you can run to start builds manually.

**Create new packages:**
```bash
lichoscli --branch 'feature/flocken' create my-new-package
```

This sets up the default branch, protection rules, and pipeline configuration.

## Advanced Workflows

### Workspace Management

**Workspaces** are collections of related packages that share a common branch context. They help manage complex multi-package development scenarios where you need to coordinate changes across multiple packages.

**Create a workspace:**
```bash
# Create workspace with a package and its reverse dependencies
lichoscli --branch feature/my-feature/flocken workspace create u-boot
```

This automatically discovers packages that depend on `u-boot` and lets you select which ones to include in the workspace.

**List available workspaces:**
```bash
# List all workspaces
lichoscli workspace list

# List workspaces containing a specific package
lichoscli workspace list u-boot
```

**Enter a workspace:**
```bash
# Interactive selection of workspace to enter
lichoscli workspace enter

# Sets LICHOS_BRANCH environment variable and opens new shell
```

**Add/remove packages:**
```bash
# Add package to existing workspace
lichoscli --branch feature/my-feature workspace add new-package

# Remove package from workspace
lichoscli --branch feature/my-feature workspace remove old-package
```

**Show workspace details:**
```bash
lichoscli workspace show

lichoscli --branch feature/my-feature workspace show
```

**Delete workspace:**
```bash
lichoscli workspace delete
```

### Build Scheduling

**Schedule sequential builds** for all packages in a workspace with dependency-aware ordering:

```bash
# Schedule builds for current workspace
lichoscli schedule

# Dry run to see what would be built
lichoscli schedule 

# Skip version checking and build everything
lichoscli schedule --skip-version-check

# Custom polling interval (default: 30 seconds)
lichoscli schedule --poll-interval 60
```

The scheduler:
- **Analyzes dependencies** to determine optimal build order
- **Checks versions** to identify packages needing rebuilds due to dependency updates
- **Builds level by level** - waits for each level to complete before starting the next
- **Monitors progress** with real-time status updates and web links
- **Stops on failure** to prevent cascading build issues

### Build Dependencies Analysis

**Analyze package dependencies** and build relationships:

**Show build dependencies:**
```bash
lichoscli buildinfo u-boot

# Use latest available data (don't wait for pipeline completion)
lichoscli buildinfo u-boot --no-wait
```

**Check dependency versions:**
```bash
# Verify reverse dependency versions
lichoscli buildinfo u-boot --check-versions

# Check if packages using u-boot have correct versions
lichoscli buildinfo u-boot --check-versions --no-wait
```

**Build dependency graph:**
```bash
# Show complete dependency DAG for all packages
lichoscli buildinfo --rev-deps

# Include version checking across all packages
lichoscli buildinfo --rev-deps --check-versions

# Use latest available buildinfo data
lichoscli buildinfo --rev-deps --no-wait
```

The DAG analysis shows:
- **Package hierarchy** with visual tree representation
- **Build levels** indicating parallel vs sequential build requirements  
- **Dependency relationships** between packages
- **Version mismatches** that require rebuilds

---

**Need more help?** Run `lichoscli --help` to see all available commands and options.

## Shell Completion

lichoscli supports tab-completion for all commands, subcommands, options, and even dynamic values like package names via [argcomplete](https://github.com/kislyuk/argcomplete).

### Installed via Debian package (automatic)

When you install the `lichoscli` `.deb` package, shell completions for **bash** and **zsh** are installed automatically to:
- `/usr/share/bash-completion/completions/lichoscli`
- `/usr/share/zsh/vendor-completions/_lichoscli`

No manual configuration is needed — open a new shell and tab-completion works.

