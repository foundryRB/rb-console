"""DeliveryOverview over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.projections.studios_index import (
    StudioStatusIndex,
)
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.domain.model.delivery_overview import (
    DeliveryOverview as DomainDeliveryOverview,
)


class DeliveryOverview:
    def __init__(
        self,
        *,
        studio_index: StudioStatusIndex | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_status: StatusPort,
    ) -> None:
        self.studio_index = studio_index
        self.cap_delivery_config = cap_delivery_config
        self.cap_status = cap_status

    def execute(self, repo: str) -> DomainDeliveryOverview:
        """A delivery's full cockpit view: its derived state plus the per-phase studio
        artifact status (does its estimatekit project / protopane prototype / platform
        app exist, and where to see each), the delivery-level config, and which records
        physically exist (so a re-opened gate shows downstream work as present-but-stale)."""
        state = self.cap_status.execute(repo)
        artifacts = {}
        if self.studio_index is not None:
            artifacts = self.studio_index.artifacts(partial(helper_slug)(state.repo))
        records = state.records_on_disk
        return DomainDeliveryOverview(
            state,
            artifacts,
            config=self.cap_delivery_config.execute(state.repo),
            records_on_disk=records,
        )
