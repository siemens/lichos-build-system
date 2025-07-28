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

**Get started with a project:**
```bash
# Clone the 00ci package to set up project detection
lichoscli --pkg-group your-group/platform-os/pkg --host gitlab.example.com clone 00ci
```

**List packages:**
```bash
# Current project
lichoscli list

# Different project
lichoscli --pkg-group your-group/platform-os/pkg --host gitlab.example.com list
```

**Check build status:**
```bash
lichoscli status
```

## Common Workflows

### Package Details

**See package configuration:**
```bash
lichoscli show keyctl-caam
```
```
Setting              Value
-------------------  -------------------------------------
id                   431660
path                 keyctl-caam
builds_access_level  enabled
ci_config_path       gbp.yml@your-group/platform-os/pkg/00ci
default_branch       flocken

Variables:
type     key    value    hidden    protected    masked    raw    scope    description
-------  -----  -------  --------  -----------  --------  -----  -------  -------------
env_var  TEST   BLUB     False     False        False     False  *        foo bar
```

### Working with Packages

**Clone a package:**
```bash
lichoscli clone keyctl-caam
```

> **Pro tip:** lichoscli automatically sets up useful remotes when cloning. If it's a fork, you get a `parent` remote for the `pdiff` command. If there's a `Repository` in `debian/upstream/metadata`, that becomes the `upstream` remote.

**Trigger a pipeline:**
```bash
cd keyctl-caam
lichoscli trigger .
# for a specific branch 
lichoscli --branch flocken . 
```

**Check pipeline status:**
```bash
 lichoscli status .   
Setting    Value
---------  --------------------------------------------------------------------------------------
sha        f0d0b325136d3ab0afcf01d7b6a27a49b77ca6f1
ref        flocken
status     success
source     push
web_url    https://github.com/samastek/lichoscli/-/pipelines/48675085

Pipeline Jobs:

       Id  Name           Stage    Status    Started
---------  -------------  -------  --------  -------------------------
284018793  publish        deploy   success   2025-07-22 07:32:18 - 35s
284018791  build-amd64    build    success   2025-07-22 07:31:31 - 24s
284018789  build-arm64    build    success   2025-07-22 07:31:32 - 45s
284018788  calculate-env  .pre     success   2025-07-22 07:31:16 - 14s
```

**View job logs:**
```bash
# Static log
lichoscli log build-amd64

# Live log (waits for job to start)
lichoscli log --wait build-amd64
```

### Local Development

**Build packages locally:**
```bash
lichoscli build . build-amd64
```

**Drop into build environment:**
```bash
# Opens a shell in the build container
lichoscli build . --shell

# sometimes if you are behind zscalar, you need to use ipv4net form docker for that 
lichoscli build . --shell --architecture arm64 --network <ip4 network name>

# Specify custom shell (use --shell= if followed by other options)
lichoscli build . --shell=/bin/zsh
```

> **Note:** Local builds are somewhat limited and expect specific pipeline layouts. The shell option prints a script you can run to start builds manually.

**Create new packages:**
```bash
lichoscli --branch 'feature/main' create my-new-package
```

This sets up the default branch, protection rules, and pipeline configuration.

---

**Need more help?** Run `lichoscli --help` to see all available commands and options.

