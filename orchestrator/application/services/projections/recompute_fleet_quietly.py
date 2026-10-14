"""Projections shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.projections.list_deliveries import (
    ListDeliveriesPort,
)
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.projections.compute_fleet import (
    helper_compute_fleet,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def helper_recompute_fleet_quietly(
    *,
    observations: ObservationStore,
    platform_repo: str,
    source: DeliverySource | None,
    studios: StudioGateway | None,
    workflows: WorkflowRunner | None,
    cap_list_deliveries: ListDeliveriesPort,
) -> None:
    """Re-derive the board after a lifecycle toggle, so the live status reflects the
    act at once. The ACT already succeeded, so an org read that fails here must not
    fail it back to the operator - and must not blank the board either (INT-FC-R144).
    The next refresh tick reconciles; until then the toggled app reads its old status,
    which is a stale row rather than a vanished floor."""
    try:
        observations.fleet = partial(
            helper_compute_fleet,
            platform_repo=platform_repo,
            source=source,
            studios=studios,
            workflows=workflows,
            cap_list_deliveries=cap_list_deliveries,
        )()
    except SourceUnavailable:
        pass
