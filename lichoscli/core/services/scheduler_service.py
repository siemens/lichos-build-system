# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Abstract scheduler service interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from lichoscli.core.models.build_schedule_result import BuildScheduleResult
from lichoscli.core.models.dag import DependencyGraph
from lichoscli.core.models.reverse_dependency_report import ReverseDependencyReport
from lichoscli.core.models.schedule_analysis import ScheduleAnalysis
from lichoscli.core.services.scheduler_listener import SchedulerListener

if TYPE_CHECKING:
    from lichoscli.core.models.project import Project
    from lichoscli.core.models.workspace import Workspace


class SchedulerService(ABC):
    """Abstract interface for DAG-based build scheduling."""

    @abstractmethod
    def prepare_schedule(
        self,
        packages: list["Project"],
        branch: str,
        skip_version_check: bool = False,
        previous_dag: Optional[DependencyGraph] = None,
    ) -> ScheduleAnalysis:
        """
        Analyse workspace packages and determine which need rebuilding.

        Builds the dependency DAG, runs version checks (unless skipped),
        marks stale nodes, and propagates rebuild requirements to
        transitive dependents.

        Returns a ScheduleAnalysis with the prepared DAG and metadata.
        """
        raise NotImplementedError

    @abstractmethod
    def analyze_reverse_dependencies(
        self,
        workspace_packages: list["Project"],
        all_packages: list["Project"],
        branch: str,
    ) -> ReverseDependencyReport:
        """Determine the reverse build dependencies of the workspace packages.

        Builds a dependency DAG across ``all_packages`` and collects the
        union of transitive dependents of every workspace package. Each
        returned entry is flagged with whether it is part of the workspace,
        so callers can surface reverse dependencies that are missing from
        the workspace and may therefore be built with stale dependencies.
        """
        raise NotImplementedError

    @abstractmethod
    def execute_schedule(
        self,
        dag: DependencyGraph,
        workspace: "Workspace",
        poll_interval: int,
        listener: SchedulerListener,
    ) -> BuildScheduleResult:
        """
        Execute the build schedule using DAG-native ordering.

        Triggers builds for ready nodes, polls pipelines until completion,
        and propagates success/failure through the graph.

        A ``SchedulerListener`` is required to receive real-time progress
        events (build triggered, succeeded, failed, polling updates).

        When ``workspace.is_protected`` is True, no workspace-scheduling
        commit statuses are posted during execution.

        Returns a BuildScheduleResult with totals.
        """
        raise NotImplementedError

    @abstractmethod
    def post_dag_statuses(
        self,
        dag: DependencyGraph,
        workspace: "Workspace",
        scheduling_complete: bool = False,
        missing_dependencies: Optional[list[str]] = None,
    ) -> None:
        """Batch-post commit statuses for all nodes in the DAG.

        Status assignment is workspace-global, not per-node:

        * **During scheduling** (``scheduling_complete=False``):
          PENDING → STALE, BUILDING → BUILDING, SUCCESS → BUILDING,
          FAILED → FAILED.  All non-failed packages are blocked from
          merging while the workspace is being rebuilt.

        * **After scheduling** (``scheduling_complete=True``):
          If any node FAILED → failed nodes get FAILED, all others
          get STALE.  If all nodes succeeded → every node gets SUCCESS.

        ``missing_dependencies`` is an optional list of reverse build
        dependencies that are not part of the workspace; when provided it
        is appended to the status description for information only and does
        not affect the reported state.

        When ``workspace.is_protected`` is True this method is a no-op:
        protected branches must not receive workspace-scheduling external
        status checks.
        """
        raise NotImplementedError

    @abstractmethod
    def send_build_notification(
        self,
        dag: DependencyGraph,
        workspace: "Workspace",
        previous_dag: Optional[DependencyGraph] = None,
    ) -> bool:
        """Send notification about build results with comparison URLs."""
        raise NotImplementedError

    @abstractmethod
    def persist_state(self, workspace: "Workspace", dag: DependencyGraph) -> None:
        """Persist the current DAG state for future comparison."""
        raise NotImplementedError

    @abstractmethod
    def await_running_pipelines(
        self,
        packages: list["Project"],
        branch: str,
        poll_interval: int,
    ) -> None:
        """Wait for any running pipelines in the workspace to complete.

        A pipeline is considered finished when its publish job has
        completed or the pipeline has reached a terminal state.
        The workspace-scheduling commit status is excluded from
        this evaluation.
        """
        raise NotImplementedError

    @abstractmethod
    def cancel_orphan_pipelines(
        self,
        packages: list["Project"],
        branch: str,
    ) -> list[str]:
        """Cancel active pipelines orphaned by a previous interrupted scheduler run."""
        raise NotImplementedError
