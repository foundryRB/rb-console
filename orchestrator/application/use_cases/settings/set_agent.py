"""SetAgent over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.team_roster import TeamRosterPort
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.driver_agent import DriverAgent
from orchestrator.application.services.definitions import _AGENT
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.present_agent import (
    helper_present_agent,
)
from orchestrator.application.services.settings.reject_invalid_credential import (
    helper_reject_invalid_credential,
)
from orchestrator.domain.exceptions.seat_refused import SeatRefused
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import (
    INSTALL,
    TEAM,
    USER,
    agent_level,
    agent_owner,
    may_manage,
)


class SetAgent:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        driver: DriverAgent | None,
        cap_team_roster: TeamRosterPort,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.driver = driver
        self.cap_team_roster = cap_team_roster
        self.admission = admission

    def _execute(
        self,
        name: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        models: list[str] | None = None,
        *,
        level: str = INSTALL,
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Save (or update) a named agent (an endpoint credential) at its owner level. The
        credential is stored in its own Secret; an empty one keeps the stored value, so
        editing the models doesn't require re-entering it. ``models`` is the list the
        endpoint serves (the default model is kept as the fallback), stored newline-joined
        so both config stores round-trip it as a plain string field. A personal agent kept
        at its level keeps its owner, whoever edits it."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        slug = partial(helper_agent_slug)(name)
        existing = self.config.get_setting(_AGENT + slug) or {}
        kept = bool(existing.get("name")) and agent_level(existing) == level
        if kept and level == USER:
            owner = str(existing.get("owner") or "")
            label = str(existing.get("owner_label") or "")
        else:
            owner = agent_owner(level, team.strip(), context)
            label = (context.principal_label or context.principal_id) if level == USER else owner
        clean = [m.strip() for m in models or [] if m and m.strip()]
        fields = {
            "name": name,
            "provider": provider or "claude",
            "base_url": base_url or "",
            "model": model or "",
            "models": "\n".join(clean),
            "level": level,
            "owner": owner,
            "owner_label": label,
        }
        self.config.put_setting(_AGENT + slug, fields, credential)
        configured = bool(credential) or bool(existing.get("configured"))
        return helper_present_agent({**fields, "configured": configured}, context)

    def execute(
        self,
        name: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        models: list[str] | None = None,
        *,
        level: str = INSTALL,
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.agent", "")
        result = []

        def dispatch():
            value = self._execute(
                name=name,
                provider=provider,
                base_url=base_url,
                model=model,
                credential=credential,
                models=models,
                level=level,
                team=team,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.agent",
            "",
            operation_id,
            safe_value(
                {
                    "name": name,
                    "provider": provider,
                    "base_url": base_url,
                    "model": model,
                    "credential": credential,
                    "models": models,
                    "level": level,
                    "team": team,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(credential),
            validate=lambda: self._validate(
                name=name,
                provider=provider,
                base_url=base_url,
                model=model,
                credential=credential,
                models=models,
                level=level,
                team=team,
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
        name: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        models: list[str] | None = None,
        *,
        level: str = INSTALL,
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        """An agent needs a name the caller may write under and a level the caller may add:
        an admin the install's, a team member their team's, anyone their own. A name another
        owner's agent holds is theirs. A given credential is validated (issue #30) before it
        is seated."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        slug = partial(helper_agent_slug)(name)
        if not slug:
            raise ValueError("an agent needs a name")
        existing = self.config.get_setting(_AGENT + slug) or {}
        if existing.get("name") and not may_manage(existing, context):
            raise SeatRefused(
                f"An agent named {existing.get('name')} already exists and is not yours to "
                "change. Choose another name."
            )
        if not (existing.get("name") and agent_level(existing) == level == USER):
            agent_owner(level, team.strip(), context)
        if level == TEAM and self.cap_team_roster.execute().team(team.strip()) is None:
            raise ValueError(f"there is no team named {team.strip()}")
        if credential:
            partial(helper_reject_invalid_credential, driver=self.driver)(
                credential, model, base_url
            )
