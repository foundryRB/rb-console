"""Refresh over consumed application contracts."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from functools import partial

from orchestrator.application.ports.inbound.projections.list_deliveries import (
    ListDeliveriesPort,
)
from orchestrator.application.ports.inbound.projections.refresh_metadata import (
    RefreshMetadataPort,
)
from orchestrator.application.ports.inbound.runs.run_graph import RunGraphPort
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.projections.studios_index import (
    StudioStatusIndex,
)
from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.definitions import logger
from orchestrator.application.services.events.narrate_positions import (
    helper_narrate_positions,
)
from orchestrator.application.services.events.narrate_terminal_runs import (
    helper_narrate_terminal_runs,
)
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.projections.compute_fleet import (
    helper_compute_fleet,
)
from orchestrator.application.services.projections.compute_inbox import (
    helper_compute_inbox,
)
from orchestrator.application.services.runs.list_run_rows import helper_list_run_rows
from orchestrator.application.services.runs.snapshot_terminal_runs import (
    helper_snapshot_terminal_runs,
)
from orchestrator.domain.exceptions.retained_evidence_unreadable import (
    RetainedEvidenceUnreadable,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.retained_execution import RetainedExecution


class Refresh:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        events: EventPublisher | None,
        index: DeliveryIndex | None,
        msource: MaintenanceSource | None,
        platform_repo: str,
        run_log_store: RunLogStore | None,
        source: DeliverySource | None,
        studio_index: StudioStatusIndex | None,
        studios: StudioGateway | None,
        workflows: WorkflowRunner | None,
        cap_list_deliveries: ListDeliveriesPort,
        cap_run_graph: RunGraphPort,
        cap_run_retention: RunRetentionPort,
        cap_refresh_metadata: RefreshMetadataPort,
        background_scope: Callable[[], AbstractContextManager] = nullcontext,
    ) -> None:
        self.background_scope = background_scope
        self.observations = observations
        self.events = events
        self.index = index
        self.msource = msource
        self.platform_repo = platform_repo
        self.run_log_store = run_log_store
        self.source = source
        self.studio_index = studio_index
        self.studios = studios
        self.workflows = workflows
        self.cap_list_deliveries = cap_list_deliveries
        self.cap_run_graph = cap_run_graph
        self.cap_run_retention = cap_run_retention
        self.cap_refresh_metadata = cap_refresh_metadata

    def execute(self, *, force: bool = False) -> int:
        """Rescan the source into the index, then refresh cross-studio status for the
        known deliveries. Called by the background refresher and by the explicit refresh
        action (POST /api/fleet/refresh, INT-FC-R107), never on a read request, so a page
        load reads warm caches (both the delivery index and the studio status). Serialized
        on a lock, so a manual rescan and the background tick never interleave. A forced
        rescan reads the inbox and every repository's metadata rather than waiting for
        their cadence.

        A tick whose org read FAILED holds the last-known board rather than replacing it
        with an empty one (INT-FC-R144), and marks it stale so the board can say so. The
        cache is a cache: its job on a bad tick is to keep answering, not to forget. The
        delivery index is marked by its own scan, so a fleet read that lands on the same
        tick never clears a held index."""
        with self.observations.refresh_lock, self.background_scope():
            n = 0
            if self.index is not None and self.source is not None:
                try:
                    n = self.index.refresh(self.source)
                    self.observations.delivery_observed_at = datetime.datetime.now(
                        datetime.UTC
                    ).isoformat()
                    self.observations.delivery_stale_since = None
                    self.observations.delivery_stale_reason = ""
                    partial(
                        helper_narrate_positions,
                        observations=self.observations,
                        events=self.events,
                        index=self.index,
                    )()
                except SourceUnavailable as exc:
                    n = -1
                    if self.observations.delivery_stale_since is None:
                        self.observations.delivery_stale_since = datetime.datetime.now(
                            datetime.UTC
                        ).isoformat(timespec="seconds")
                    self.observations.delivery_stale_reason = str(exc)
            if self.studio_index is not None and self.studios is not None:
                slugs = [
                    partial(helper_slug)(s.repo)
                    for s in self.cap_list_deliveries.execute()
                ]
                try:
                    self.studio_index.refresh(self.studios, slugs)
                except SourceUnavailable:
                    n = -1
            try:
                self.observations.fleet = partial(
                    helper_compute_fleet,
                    platform_repo=self.platform_repo,
                    source=self.source,
                    studios=self.studios,
                    workflows=self.workflows,
                    cap_list_deliveries=self.cap_list_deliveries,
                )()
                self.observations.fleet_stale_since = None
                self.observations.fleet_stale_reason = ""
            except SourceUnavailable as exc:
                if self.observations.fleet_stale_since is None:
                    self.observations.fleet_stale_since = datetime.datetime.now(
                        datetime.UTC
                    ).isoformat(timespec="seconds")
                self.observations.fleet_stale_reason = str(exc)
            try:
                run_rows = partial(helper_list_run_rows, workflows=self.workflows)()
            except SourceUnavailable:
                logger.warning("Run collection unavailable", exc_info=True)
                run_rows = list(self.observations.runs)
                n = -1
            partial(
                helper_snapshot_terminal_runs,
                run_log_store=self.run_log_store,
                workflows=self.workflows,
                cap_run_retention=self.cap_run_retention,
            )(run_rows)
            partial(
                helper_narrate_terminal_runs,
                observations=self.observations,
                events=self.events,
                cap_run_graph=self.cap_run_graph,
            )(run_rows)
            report = self.cap_refresh_metadata.execute(sweep=force)
            self.observations.inbox_tick += 1
            if self.msource is not None and (
                force or self.observations.inbox_tick % 5 == 1
            ):
                try:
                    self.observations.inbox = helper_compute_inbox(
                        observations=self.observations
                    )
                except Exception:  # noqa: BLE001 - boundary failure is logged or propagated
                    logger.warning("Inbox observation failed", exc_info=True)
                    n = -1
            run_metadata = self.observations.metadata.setdefault("", {})
            graphs = dict(self.observations.graphs)
            statuses = dict(run_metadata.get("statuses") or {})
            for row in run_rows:
                handle = str(row.handle or "")
                if not handle:
                    continue
                try:
                    graph = self.workflows.graph(handle)
                    graphs[handle] = graph
                    statuses[handle] = str(graph.phase or row.phase or "unknown")
                    if self.run_log_store is not None:
                        self.run_log_store.save_metadata(
                            str(row.name or handle.rsplit("/", 1)[-1]),
                            RetainedExecution(row, graph),
                        )
                except Exception:  # noqa: BLE001 - boundary failure is logged or propagated
                    logger.warning("Run observation failed: %s", handle, exc_info=True)
                    n = -1
            retained: list[RetainedExecution] = []
            try:
                if self.run_log_store is not None:
                    retained = self.run_log_store.all_metadata()
            except RetainedEvidenceUnreadable as exc:
                # An unreadable record withholds only itself: the records read still merge,
                # and the tick still reports the archive unavailable.
                logger.warning("Retained execution collection incomplete: %s", exc)
                retained = list(exc.retained)
                n = -1
            except SourceUnavailable:
                logger.warning(
                    "Retained execution collection unavailable", exc_info=True
                )
                n = -1
            for archived in retained:
                row = archived.run
                handle = str(row.handle or "")
                if handle and handle not in graphs:
                    graphs[handle] = archived.graph
                    statuses[handle] = str(
                        graphs[handle].phase or row.phase or "unknown"
                    )
                if handle and (not any(r.handle == handle for r in run_rows)):
                    run_rows.append(row)
            self.observations.graphs = graphs
            run_metadata["statuses"] = statuses
            self.observations.runs = run_rows
            board = self.observations.metadata.setdefault("", {})
            previous = board.get("freshness") or {}
            unavailable = n < 0 or self.observations.fleet_stale_since is not None
            now = datetime.datetime.now(datetime.UTC).isoformat()
            board["freshness"] = {
                "state": ("stale" if previous.get("observed_at") else "unavailable")
                if unavailable
                else "fresh"
                if report["complete"]
                else "stale",
                "observed_at": previous.get("observed_at") if unavailable else now,
                "last_attempt_at": now,
                "reason_code": "source_unavailable"
                if unavailable
                else ""
                if report["complete"]
                else "partial_collection",
                "coverage": {
                    "complete": report["complete"] and not unavailable,
                    "observed": report["observed"],
                    "total": report["total"],
                },
            }
            return n
