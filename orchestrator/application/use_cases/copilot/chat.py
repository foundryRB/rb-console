"""Chat over consumed application contracts."""

from __future__ import annotations

import logging
import re
from functools import partial

from orchestrator.application.ports.inbound.content.repo_file import RepoFilePort
from orchestrator.application.ports.inbound.maintenance.maintenance_positions import (
    MaintenancePositionsPort,
)
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.driver_agent import DriverAgent
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.copilot.maintenance_chat import (
    helper_maintenance_chat,
)
from orchestrator.application.services.definitions import REF_DELIVERY_DIGEST
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.settings.has_delivery_cred import (
    helper_has_delivery_cred,
)
from orchestrator.domain.delivery import NOT_A_DELIVERY, SCRATCH
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import refuse_foreign_seat


class Chat:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        credentials: CredentialStore | None,
        driver: DriverAgent | None,
        workflows: WorkflowRunner | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_maintenance_positions: MaintenancePositionsPort,
        cap_repo_file: RepoFilePort,
        cap_status: StatusPort,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.driver = driver
        self.workflows = workflows
        self.cap_delivery_config = cap_delivery_config
        self.cap_maintenance_positions = cap_maintenance_positions
        self.cap_repo_file = cap_repo_file
        self.cap_status = cap_status

    def execute(
        self,
        repo: str,
        phase: str,
        message: str,
        history=None,
        references=None,
        *,
        viewer: CommandContext | None = None,
    ) -> dict:
        """One turn with the project co-pilot. The voice is scoped: an OPEN delivery speaks
        only through its own agent (the masthead pick, persisted by slug) - it never
        silently borrows the home driver, so the operator always knows which agent answers.
        Only a repo with NO open line (the project view) falls back to the home co-pilot's
        driver, because there is no delivery to carry an agent there. Degrades to a
        not-configured hint until the right credential exists (never fabricates a reply)."""
        if self.driver is None:
            return {"reply": None, "configured": False, "model": None}
        state = self.cap_status.execute(repo)
        credential, model, base_url = ("", "", "")
        if partial(helper_has_delivery_cred, credentials=self.credentials)(
            partial(helper_slug)(repo)
        ):
            dc = self.cap_delivery_config.execute(repo)
            # The line's agent answers its co-pilot, so a personal seat answers its owner.
            if viewer is not None:
                refuse_foreign_seat(dc, viewer)
            credential, model, base_url = (
                self.credentials.get_delivery(partial(helper_slug)(repo)),
                dc["model"],
                dc["base_url"],
            )
        elif state.status == NOT_A_DELIVERY and self.config is not None:
            d = self.config.get_setting("driver")
            credential, model, base_url = (
                self.config.get_secret("driver"),
                d.get("model", ""),
                d.get("base_url", ""),
            )
        if not credential:
            return {"reply": None, "configured": False, "model": None}
        if (phase or "").strip() == "maintenance":
            return partial(
                helper_maintenance_chat,
                driver=self.driver,
                cap_maintenance_positions=self.cap_maintenance_positions,
            )(repo, message, history, credential, model, base_url)
        cfg = self.cap_delivery_config.execute(repo)
        here = phase or state.phase or ""
        parts = [
            f"You are the delivery co-pilot for {repo}, a REF-Delivery engagement.",
            REF_DELIVERY_DIGEST,
            f"Current phase: {here}. Overall status: {state.status}. Mode: {cfg['mode']}.",
        ]
        ph = next((p for p in state.lifecycle.phases if p.name == here), None)
        if ph and ph.question:
            parts.append(f"The question this phase answers: {ph.question}")
        parts.append(
            f"Committed records: {', '.join(state.records_present) or 'none yet'}."
        )
        if ph and ph.record:
            rec = self.cap_repo_file.execute(repo, f"{SCRATCH}/{ph.record}")
            if rec.content:
                parts.append(
                    f"\n--- {ph.record} (this phase's record, committed by its worker) ---\n{rec.content[:6000]}"
                )
        if self.workflows is not None:
            try:
                mine = [
                    r
                    for r in self.workflows.list_runs()
                    if r.repository == repo and r.kind == "delivery"
                ]
                if mine:
                    newest = mine[0]
                    tail = (
                        self.workflows.logs(newest.handle, 50) if newest.handle else ""
                    )
                    if tail:
                        parts.append(
                            f"\n--- the latest run's log tail ({newest.name} · {newest.phase}) ---\n"
                            + tail[-6000:]
                        )
            except Exception:
                logging.getLogger(__name__).warning(
                    "Run context is unavailable for the advisory turn", exc_info=True
                )
        for ref in (references or [])[:10]:
            path, lines = (ref, None)
            m = re.match("^(.*)#L(\\d+)(?:-L?(\\d+))?$", ref)
            if m:
                path = m.group(1)
                start = int(m.group(2))
                end = int(m.group(3) or m.group(2))
                lines = (max(1, start), max(start, end))
            got = self.cap_repo_file.execute(repo, path)
            content = got.content
            if not content:
                continue
            if lines:
                sliced = "\n".join(content.splitlines()[lines[0] - 1 : lines[1]])
                parts.append(
                    f"\n--- {path} (lines {lines[0]}-{lines[1]}) ---\n{sliced[:8000]}"
                )
            else:
                parts.append(f"\n--- {path} ---\n{content[:8000]}")
        parts.append(
            "Help the operator reason about this phase, using its record above and any referenced files. Be concise and concrete, with ASCII punctuation only (no em-dashes). You advise; you never execute. You are toolless BY DESIGN - the console's determinism lives in operator-pressed acts and compiled workers - so never attempt a tool call and never claim you ran anything. The operator's controls beside you: Sign (accept the gate, release the next phase), Re-drive with feedback (reject the gate and re-run this phase as a revision), Drive / Drive from here (compile the remaining line), and the delivery's mode config. Advise by naming the control and what to put in it. When the conversation converges on what this phase should change, end your reply with a fenced code block tagged `redrive` containing ONLY the feedback - imperative, concrete, nothing that was not discussed. The console stages that block into the gate's Re-drive composer for the operator to edit and fire; writing it executes nothing."
        )
        system = "\n".join(parts)
        messages = list(history or []) + [{"role": "user", "content": message}]
        reply = self.driver.chat(
            system, messages, credential=credential, model=model, base_url=base_url
        )
        return {"reply": reply, "configured": True, "model": model or "haiku"}
