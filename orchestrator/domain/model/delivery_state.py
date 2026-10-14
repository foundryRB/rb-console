"""DeliveryState delivery value."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.model.gate_state import GateState
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition


@dataclass(frozen=True)
class DeliveryState:
    """Everything derivable about a delivery, from its scratch alone."""

    repo: str
    exists: bool  # the scratch is present (the line's delivery/* ref; locally, the .delivery/ mount)
    status: str
    phase: str | None
    next_skill: str | None
    next_command: str | None
    blocked_gate: str | None
    gates: tuple[GateState, ...]
    records_present: tuple[str, ...]
    #: The date reconcile-delivery stamped into the journal frontmatter, once Learn
    #: has executed (status LEARNED); None until then.
    learned_on: str | None = None
    #: The line's resolved scratch ref (the ``delivery/<line-id>`` branch name), per-repo
    #: state the source resolves at read time. Empty when the source cannot know it (the
    #: local filesystem read) or when the repo carries no line.
    scratch_ref: str = ""
    #: What the line grows from - SEED_NEW, SEED_FOLLOW_ON, SEED_RECAST, or SEED_DEMO - read
    #: off the repo's tags (and, for a demo, the org's source repo) by the source at read
    #: time (derive_seed), never declared. Empty when the source cannot read the tags (the
    #: local filesystem read, an unreadable namespace): an unseen fact is reported as
    #: unseen, never as new.
    seed: str = ""
    #: The line a demo rehearses (REF-Demo): the source repository's full name, read by the
    #: source when the repo is named ``demo-<x>`` and the org holds ``<x>`` as a line.
    #: Empty for every other seed.
    demo_of: str = ""
    revision: str = ""
    repository_id: str = ""
    lifecycle: LifecycleDefinition = CURRENT_LIFECYCLE
    records_on_disk: tuple[str, ...] = ()
    reviewed_records: tuple[str, ...] = ()
