"""Events shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.events import RUN_COMPLETED, state_fact
from orchestrator.application.ports.inbound.runs.run_graph import RunGraphPort
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.services.definitions import _TERMINAL_RUN_PHASES
from orchestrator.application.services.runs.terminal_exit_of import (
    helper_terminal_exit_of,
)
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.run_policy import stop_name


def helper_narrate_terminal_runs(
    rows: list[RunInventoryEntry],
    *,
    observations: ObservationStore,
    events: EventPublisher | None,
    cap_run_graph: RunGraphPort,
) -> None:
    """State each run that turned terminal since the last tick, once. The first tick
    primes the seen set and states nothing, for the same reason as the positions."""
    terminal = {
        str(r.name or ""): r for r in rows if r.name and r.phase in _TERMINAL_RUN_PHASES
    }
    if observations.terminal_seen is None:
        observations.terminal_seen = set(terminal)
        return
    for name, r in terminal.items():
        if name in observations.terminal_seen:
            continue
        observations.terminal_seen.add(name)
        failed = r.phase in ("Failed", "Error")
        stop = (
            stop_name(
                partial(helper_terminal_exit_of, cap_run_graph=cap_run_graph)(
                    str(r.handle or "")
                )
            )
            if failed
            else ""
        )
        state_fact(
            events,
            event_type=RUN_COMPLETED,
            subject=name,
            data={
                "run": name,
                "handle": r.handle,
                "repo": r.repository_slug,
                "phase": r.phase,
                "stop": stop,
                "mode": r.mode,
                "maintenance": r.maintenance_act,
                "ticket": r.ticket,
            },
        )
    if rows:
        observations.terminal_seen &= set(terminal)
