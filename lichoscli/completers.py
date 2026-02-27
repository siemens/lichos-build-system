# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Argument completers for shell autocompletion via argcomplete."""


from __future__ import annotations

import argparse
import os
from typing import Any

# ---------------------------------------------------------------------------
# DI container bootstrap (lightweight — for completion only)
# ---------------------------------------------------------------------------

def _build_container(parsed_args: argparse.Namespace):
    """Create a DI container from the partially-parsed args.

    During completion the user may already have typed ``--host`` or
    ``--pkg-group``; those values live in *parsed_args*.  We build a
    ``LichosConfig`` and create the container so completers can access
    services like ``PackageService``.

    Returns ``None`` when the container cannot be created (e.g. no host
    detected).
    """
    try:
        from lichoscli.core.config import ConfigBuilder
        from lichoscli.core.container_factory import DIContainerFactory

        config = ConfigBuilder(parsed_args).build()
        if not config.host or not config.pkg_group:
            return None
        return DIContainerFactory.create(config)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Completers
# ---------------------------------------------------------------------------

class WorkspaceCompleter:
    """Complete workspace (branch) names from GitLab."""

    def __call__(self, prefix: str, parsed_args: argparse.Namespace, **kwargs) -> list[str]:
        try:
            from lichoscli.core.services import WorkspaceService
            container = _build_container(parsed_args)
            if container is None:
                return []
            ws_svc = container.obtain_ref(WorkspaceService)
            workspaces = ws_svc.list_workspaces()
            return sorted(w.name for w in workspaces if w.name.startswith(prefix))
        except Exception:
            return []


class JobCompleter:
    """Complete CI job names for a given package.

    Uses the package already typed on the command line.  Falls back to a
    static list of common job names when the package is not yet known.
    """

    FALLBACK_JOBS = [
        "build-amd64",
        "build-arm64",
        "publish",
    ]

    def __call__(self, prefix: str, parsed_args: argparse.Namespace, **kwargs) -> list[str]:
        try:
            package = getattr(parsed_args, "package", None)
            if not package:
                return [j for j in self.FALLBACK_JOBS if j.startswith(prefix)]

            from lichoscli.core.services import PackageService
            container = _build_container(parsed_args)
            if container is None:
                return [j for j in self.FALLBACK_JOBS if j.startswith(prefix)]

            pkg_svc = container.obtain_ref(PackageService)
            pkg = pkg_svc.get_package(package)
            if pkg is None:
                return [j for j in self.FALLBACK_JOBS if j.startswith(prefix)]

            branch = getattr(parsed_args, "branch", None) or os.environ.get("LICHOS_BRANCH")
            pipeline = pkg.pipelines.get_latest(branch or pkg.default_branch)
            if pipeline is None:
                return [j for j in self.FALLBACK_JOBS if j.startswith(prefix)]

            return sorted(j for j in set(job.name for job in pipeline.jobs)
                          if j.startswith(prefix))
        except Exception:
            return []


class DockerNetworkCompleter:
    """Complete Docker network names from the local Docker daemon."""

    def __call__(self, prefix: str, parsed_args: argparse.Namespace, **kwargs) -> list[str]:
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "network", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
            names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return sorted(n for n in names if n.startswith(prefix))
        except Exception:
            return []


class BranchCompleter:
    """Complete branch names from the local git repository.

    Reads local branches from the git repo containing the current working
    directory — no network call, no configuration required.

    The completer always returns a non-None result so that argcomplete
    marks the argument as "handled" and suppresses zsh/bash filesystem
    fallback even when the result set is empty (e.g. detached HEAD).
    """

    def __call__(self, prefix: str, parsed_args: argparse.Namespace, **kwargs) -> list[str]:
        try:
            from git import Repo
            from git.refs.remote import RemoteReference

            repo = Repo(search_parent_directories=True)

            # Local branches — always included.
            local_names: set[str] = {b.name for b in repo.branches}

            # Remote-tracking branches whose short name (i.e. after stripping
            # the "<remote>/" prefix) does not already exist locally.  This
            # mirrors the default --guess behaviour of `git switch <TAB>`.
            remote_only: set[str] = set()
            for ref in repo.references:
                if isinstance(ref, RemoteReference):
                    # ref.name is e.g. "origin/feature" → short name "feature"
                    _, _, short = ref.name.partition("/")
                    if short and short != "HEAD" and short not in local_names:
                        remote_only.add(short)

            return sorted(
                n for n in (local_names | remote_only) if n.startswith(prefix)
            )
        except Exception:
            # Not in a git repo or GitPython error — return empty list.
            # argcomplete will see no completions and will not fall back to
            # filesystem because the completer IS registered on the action.
            return []


# ---------------------------------------------------------------------------
# Completer ↔ dest-name mapping
# ---------------------------------------------------------------------------
# To extend: add an entry here.  Any command that uses the same dest name
# automatically gets dynamic completion without further changes.

_job_completer = JobCompleter()
_workspace_completer = WorkspaceCompleter()
_branch_completer = BranchCompleter()
_docker_network_completer = DockerNetworkCompleter()

DEST_COMPLETER_MAP: dict[str, Any] = {
    "job":            _job_completer,
    "job_name":       _job_completer,        # collect_sources: --job-name
    "workspace_name": _workspace_completer,
    "branch":         _branch_completer,
    "ci_branch":      _branch_completer,     # enable: --ci-branch
    "network":        _docker_network_completer,
}


# ---------------------------------------------------------------------------
# Parser walker — the core integration point
# ---------------------------------------------------------------------------

def attach_completers(parser: argparse.ArgumentParser) -> None:
    """Recursively assign completers to all matching actions in *parser*.

    Walks the full parser tree (including nested subparsers) and sets
    ``action.completer`` for every action whose ``dest`` is in
    ``DEST_COMPLETER_MAP``.  New commands automatically receive completion
    for any argument that follows the naming convention.
    """
    _walk_parser(parser, set())


def _walk_parser(parser: argparse.ArgumentParser, seen: set) -> None:
    """Depth-first traversal of the parser tree, guarded against cycles."""
    parser_id = id(parser)
    if parser_id in seen:
        return
    seen.add(parser_id)

    for action in parser._actions:
        if action.dest in DEST_COMPLETER_MAP:
            action.completer = DEST_COMPLETER_MAP[action.dest]

        if isinstance(action, argparse._SubParsersAction):
            for subparser in action.choices.values():
                _walk_parser(subparser, seen)
