from dataclasses import dataclass


@dataclass(frozen=True)
class RunInventoryEntry:
    handle: str
    name: str
    phase: str
    run_id: str | None = None
    repository: str | None = None
    resource_version: str | None = None
    grant_id: str | None = None
    mode: str | None = None
    kind: str | None = None
    promotion_target: str | None = None
    maintenance_act: str | None = None
    ticket: int | None = None
    repository_slug: str | None = None
    parked_gate: str | None = None
    stop_reason: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    progress: str | None = None
    agents: tuple[str, ...] = ()
