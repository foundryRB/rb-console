"""PromotionState over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.promotion import promotion_view
from orchestrator.application.release_train import latest_version


class CollectPromotionState:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        door: Door | None,
        msource: MaintenanceSource | None,
        psource: PromotionSource | None,
        cap_pair_credential_held: PairCredentialHeldPort,
    ) -> None:
        self.config = config
        self.door = door
        self.msource = msource
        self.psource = psource
        self.cap_pair_credential_held = cap_pair_credential_held

    def execute(self, repo: str) -> dict:
        """One repo's promotion mode: what its contract declares, where each target
        stands, and the queue (REF-Promotion sections 2 to 6).

        The proven release is the version the entry environment serves, which is the
        release train's own reading of this repo; targets and their accepted state
        come from the app's contract and its deploy branches. An app with no contract
        is not a promotion subject, and says so rather than showing an empty queue.
        """
        if self.psource is None:
            return {
                "repo": repo,
                "declared": False,
                "problem": "",
                "proven": "",
                "targets": [],
            }
        proven = (
            latest_version(self.msource.tags(repo)) if self.msource is not None else ""
        )
        view = promotion_view(
            repo=repo,
            proven=proven,
            source=self.psource,
            registered=self.cap_pair_credential_held.execute
            if self.config is not None
            else None,
            has_entry_environment=bool(self.psource.deploy_installs(repo)),
            door=self.door,
        )
        return {
            "repo": repo,
            "declared": view["declared"],
            "problem": view["problem"],
            "proven": view["proven"],
            "subject": view.get("subject", ""),
            "targets": [
                {
                    "name": p.target.name,
                    "kind": p.target.kind.value,
                    "destination": p.target.destination,
                    "door": p.target.door,
                    "terms": p.target.terms,
                    "acceptance": p.target.acceptance,
                    "credential": p.target.credential,
                    "state": p.state.value,
                    "accepted": p.accepted,
                    "door_ref": p.door_ref,
                    "detail": p.detail,
                    "door_shut": p.door_shut,
                }
                for p in view["queue"]
                + [q for q in view["positions"] if q not in view["queue"]]
            ],
        }
