"""SetTargetSelection over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.repositories.repository_incarnations import (
    RepositoryIncarnations,
)
from orchestrator.application.services.definitions import _MIN_TIMEOUT_SECONDS, _TARGET
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext

#: The applied agent's owner, recorded beside the selection.
_SEAT_FIELDS = ("agent_level", "agent_owner", "agent_owner_label")


class SetTargetSelection:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        incarnations: RepositoryIncarnations,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.incarnations = incarnations
        self.admission = admission

    def _execute(
        self,
        repo: str,
        agent: str,
        provider: str,
        base_url: str,
        model: str,
        timeout_seconds: int | None = None,
        *,
        seat: dict | None = None,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        """Persist a target's model selection Console-local (never git; R45/R72): which saved
        agent backs it and the model chosen on that agent. No secret - the credential is the
        per-slug Secret, seated separately. Identical for a delivery and a maintenance-only repo.

        ``timeout_seconds`` is the worker's wall-clock budget; when None the stored one is
        PRESERVED - a model or agent change (both route through here) must never silently reset
        the run budget, and put_setting replaces the whole field set, so preserve it explicitly."""
        if self.config is None:
            return
        self.incarnations.adopt(repo)
        fields = {
            "agent": agent or "",
            "provider": provider or "claude",
            "base_url": base_url or "",
            "model": model or "",
        }
        existing = self.config.get_setting(_TARGET + partial(helper_slug)(repo)) or {}
        # Who owns the seated key: what a drive checks a personal seat against. Applying an
        # agent records its owner and seating a typed credential clears it; a write that
        # keeps the key (a model, endpoint or timeout change) keeps its owner.
        held = seat if seat is not None else existing
        for key in _SEAT_FIELDS:
            if held.get(key):
                fields[key] = str(held[key])
        if timeout_seconds is None:
            if existing.get("timeout_seconds") not in (None, ""):
                fields["timeout_seconds"] = str(existing["timeout_seconds"])
        else:
            fields["timeout_seconds"] = str(
                max(int(timeout_seconds), _MIN_TIMEOUT_SECONDS)
            )
        self.config.put_setting(_TARGET + partial(helper_slug)(repo), fields, None)

    def execute(
        self,
        repo: str,
        agent: str,
        provider: str,
        base_url: str,
        model: str,
        timeout_seconds: int | None = None,
        *,
        seat: dict | None = None,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        context.authorize("settings.target", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                agent=agent,
                provider=provider,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                seat=seat,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.target",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "agent": agent,
                    "provider": provider,
                    "base_url": base_url,
                    "model": model,
                    "timeout_seconds": timeout_seconds,
                    "seat": seat,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                agent=agent,
                provider=provider,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                seat=seat,
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
        agent: str,
        provider: str,
        base_url: str,
        model: str,
        timeout_seconds: int | None = None,
        *,
        seat: dict | None = None,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        """Persist a target's model selection Console-local (never git; R45/R72): which saved
        agent backs it and the model chosen on that agent. No secret - the credential is the
        per-slug Secret, seated separately. Identical for a delivery and a maintenance-only repo.

        ``timeout_seconds`` is the worker's wall-clock budget; when None the stored one is
        PRESERVED - a model or agent change (both route through here) must never silently reset
        the run budget, and put_setting replaces the whole field set, so preserve it explicitly."""
        if self.config is None:
            return
        fields = {
            "agent": agent or "",
            "provider": provider or "claude",
            "base_url": base_url or "",
            "model": model or "",
        }
        if timeout_seconds is None:
            existing = (
                self.config.get_setting(_TARGET + partial(helper_slug)(repo)) or {}
            )
            if existing.get("timeout_seconds") not in (None, ""):
                fields["timeout_seconds"] = str(existing["timeout_seconds"])
        else:
            fields["timeout_seconds"] = str(
                max(int(timeout_seconds), _MIN_TIMEOUT_SECONDS)
            )
