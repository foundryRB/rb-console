"""Copilot shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.maintenance.maintenance_positions import (
    MaintenancePositionsPort,
)
from orchestrator.application.ports.outbound.driver_agent import DriverAgent
from orchestrator.application.services.definitions import REF_MAINTENANCE_DIGEST


def helper_maintenance_chat(
    repo: str,
    message: str,
    history,
    credential: str,
    model: str,
    base_url: str,
    *,
    driver: DriverAgent | None,
    cap_maintenance_positions: MaintenancePositionsPort,
) -> dict:
    """One maintenance-context co-pilot turn: the REF-Maintenance digest, the derived
    train and positions, and the tab's actual controls. Advisory and toolless, like
    every co-pilot turn."""
    pos = cap_maintenance_positions.execute(repo)
    train = pos.train
    lines = [f"- issue #{i.number}: {i.title}" for i in pos.issues[:20]] + [
        f"- PR #{p.number}: {p.title} (verdict: {p.verdict}, checks: {p.checks}"
        + (", contributor" if p.contributor else "")
        + ")"
        for p in pos.prs[:20]
    ]
    system = "\n".join(
        [
            f"You are the maintenance co-pilot for {repo}.",
            REF_MAINTENANCE_DIGEST,
            f"The release train: version {train.version or 'none'}, {train.unreleased_total} unreleased commit(s)"
            + (
                f", next would cut {train.next_version}"
                if train.next_version
                else ", nothing to cut"
            )
            + (f", deployed {train.deployed}" if train.deployed else "")
            + ".",
            "The loop positions:",
            *(lines or ["- nothing open: the loop is drained"]),
            "The operator's controls beside you, all operator-pressed: Resolve a ticket (gated / one-shot / direct, gated default), Review a PR (a fresh-eyes worker), Merge (gated mode, over a PASS), Reconcile docs (a check run), and the fleet inbox on the home page. Advise concisely with ASCII punctuation only (no em-dashes); name the exact control. You never execute anything: you are toolless by design, so never attempt a tool call and never claim you ran anything.",
        ]
    )
    messages = list(history or []) + [{"role": "user", "content": message}]
    reply = driver.chat(
        system, messages, credential=credential, model=model, base_url=base_url
    )
    return {"reply": reply, "configured": True, "model": model or "haiku"}
