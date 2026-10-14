"""PlanNext over consumed application contracts."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.settings.has_delivery_cred import (
    helper_has_delivery_cred,
)
from orchestrator.application.services.settings.with_delivery_config import (
    helper_with_delivery_config,
)
from orchestrator.domain.delivery import AWAITING_GATE, NOT_A_DELIVERY
from orchestrator.domain.model.delivery.next_action import NextAction
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.services.delivery_launch import build_worker_launch


class PlanNext:
    def __init__(
        self,
        *,
        credentials: CredentialStore | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_status: StatusPort,
    ) -> None:
        self.credentials = credentials
        self.cap_delivery_config = cap_delivery_config
        self.cap_status = cap_status

    def execute(self, repo: str, config: RunConfig) -> NextAction:
        state = self.cap_status.execute(repo)
        if state.status == NOT_A_DELIVERY:
            return NextAction("needs-start", state)
        if state.status == AWAITING_GATE:
            return NextAction("await-gate", state, gate=state.blocked_gate)
        config = helper_with_delivery_config(
            repo, config, cap_delivery_config=self.cap_delivery_config
        )
        slug = helper_slug(repo)
        if not config.worker_credential and helper_has_delivery_cred(
            slug, credentials=self.credentials
        ):
            ref = (
                self.credentials.delivery_ref(slug)
                if self.credentials is not None
                else ""
            )
            config = replace(config, worker_credential=ref)
        launch = build_worker_launch(repo, state.phase, state.next_skill or "", config)
        return NextAction("launch", state, launch=launch)
