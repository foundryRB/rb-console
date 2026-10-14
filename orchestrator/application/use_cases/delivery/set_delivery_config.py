"""SetDeliveryConfig over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.services.definitions import _MODES
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.raw_config import helper_raw_config
from orchestrator.domain.model.command_context import CommandContext


class SetDeliveryConfig:
    def __init__(
        self,
        *,
        repos: RepoStore,
        source: DeliverySource | None,
        cap_delivery_config: DeliveryConfigPort,
        admission: OperationAdmission,
        observations: ObservationStore,
    ) -> None:
        self.repos = repos
        self.source = source
        self.cap_delivery_config = cap_delivery_config
        self.admission = admission
        self.observations = observations

    def _execute(
        self,
        repo: str,
        mode: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Apply the admitted set delivery config command using its prepared inputs."""
        if mode not in _MODES:
            raise ValueError(f"unknown mode {mode!r}")
        cfg = partial(helper_raw_config, source=self.source)(repo)
        cfg.pop("presence", None)
        cfg.update({"mode": mode})
        self.repos.write_config(repo, cfg)
        # The answer carries the mode just committed, never a re-read of the branch, and the
        # line's observed configuration takes it at once: reads serve the observed projection,
        # which metadata collection would otherwise bring up to date only when the repository
        # is next due (INT-FC-R178).
        answer = {**self.cap_delivery_config.execute(repo), "mode": mode}
        observed = self.observations.metadata.get(repo, {})
        self.observations.metadata[repo] = {**observed, "delivery_config": answer}
        return answer

    def execute(
        self,
        repo: str,
        mode: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("delivery.configure", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                mode=mode,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.configure",
            repo,
            operation_id,
            safe_value(
                {"repo": repo, "mode": mode, "expected_revision": expected_revision}
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                mode=mode,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            ),
        )
        if result:
            return result[0]
        return restore_result(
            retained, get_type_hints(self._execute).get("return", object)
        )

    def _validate(
        self,
        repo: str,
        mode: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Validate fresh set delivery config preconditions before recording command intent."""
        if mode not in _MODES:
            raise ValueError(f"unknown mode {mode!r}")
        cfg = partial(helper_raw_config, source=self.source)(repo)
        cfg.pop("presence", None)
        cfg.update({"mode": mode})
