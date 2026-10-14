"""MaintenanceState over consumed application contracts."""

from __future__ import annotations

from dataclasses import asdict
from functools import partial

from orchestrator.application.ports.inbound.maintenance.maintenance_positions import (
    MaintenancePositionsPort,
)
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.services.promotion.home_target import helper_home_target
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.services.maintenance_launch import ACT_SKILLS


class CollectMaintenanceState:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        psource: PromotionSource | None,
        cap_instantiation: InstantiationPort,
        cap_maintenance_positions: MaintenancePositionsPort,
        cap_status: StatusPort,
    ) -> None:
        self.observations = observations
        self.psource = psource
        self.cap_instantiation = cap_instantiation
        self.cap_maintenance_positions = cap_maintenance_positions
        self.cap_status = cap_status

    def execute(self, repo: str, include_hidden: bool = True) -> dict:
        """The Maintenance tab's three concerns for one repo, mid-delivery included
        (INT-FC-R62): STATE (train + positions), ACTION (the drive surface with its
        modes, gated default), and where the delivery line stands beside it.

        A ticket carrying the 'foundry-hidden' label is excluded from the pane's issue
        positions by default - the issue-scope mirror of the Fleet's hide (INT-FC-R47/R96)
        extended to the maintenance pane, so a ticket switched to a delivery line leaves the
        loop (INT-FC-R100). ``include_hidden`` reveals them, exactly as it does for the Fleet
        and the Inbox, so a deep-link to a hidden ticket still resolves when the operator asks."""
        pos = self.cap_maintenance_positions.execute(repo)
        delivery = self.cap_status.execute(repo)
        driven = [
            {
                "handle": h,
                "repo": e["repo"],
                "ticket": e["ticket"],
                "acted": e["acted"],
                "result": e["result"],
            }
            for h, e in self.observations.oneshot.items()
            if e["repo"] == repo
        ]
        positions = asdict(pos)
        if not include_hidden:
            positions["issues"] = [
                i
                for i in positions["issues"]
                if "foundry-hidden" not in (i.get("labels") or [])
            ]
        home = partial(
            helper_home_target,
            psource=self.psource,
            cap_instantiation=self.cap_instantiation,
        )(repo)
        modes = list(MaintenanceMode)
        return {
            "repo": repo,
            "positions": positions,
            "action": {
                "acts": list(ACT_SKILLS),
                "modes": [m.value for m in modes],
                "default_mode": MaintenanceMode.GATED.value,
            },
            "delivery": {"status": delivery.status, "phase": delivery.phase},
            "driven": driven,
            "home": {
                "repo": home.repo,
                "branch": home.branch,
                "credential": home.credential,
            }
            if home is not None
            else None,
        }
