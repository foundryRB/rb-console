"""DeliveryOverview domain value."""
from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.studio_artifact import StudioArtifact


@dataclass(frozen=True)
class DeliveryOverview:
    """A delivery's full cockpit view: its derived state plus the per-phase studio
    artifact status, keyed by artifact identity (only artifacts backed by a studio appear).

    ``config`` is the delivery-level mode (how its runs execute).
    ``records_on_disk`` is which phase records physically exist, independent of the
    resolver's truncation, so a re-opened gate shows downstream work as present-but-stale.
    """

    state: DeliveryState
    artifacts: dict[str, StudioArtifact]
    config: dict = field(default_factory=dict)
    records_on_disk: tuple[str, ...] = ()
