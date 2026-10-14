"""Read a mounted delivery scratch and resolve its committed records."""
from pathlib import Path

from orchestrator.adapters.outbound.records.yaml_record_parser import parse_record
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.delivery import JOURNAL, SCRATCH
from orchestrator.domain.model.delivery_record import DeliveryRecord
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.services.delivery_resolution import derive_from_records


def derive_state(repo_path: str | Path, definition: LifecycleDefinition = CURRENT_LIFECYCLE) -> DeliveryState:
    """Derive a delivery's state by reading its ``.delivery/`` from the local filesystem.

    ``.delivery/`` is where a working checkout mounts the line's scratch ref as a linked
    worktree, so this reads the mount's view: a checkout whose ref exists but is not
    mounted has no ``.delivery/`` on disk and reads as not-a-delivery here - the local
    source answers for what is materialised, and the remote source answers for the ref.
    """
    repo = Path(repo_path)
    scratch = repo / SCRATCH
    exists = scratch.is_dir()
    contents: dict[str, DeliveryRecord] = {}
    if exists:
        for phase in definition.phases:
            record = scratch / phase.record
            if not record.is_file():
                continue
            contents[phase.record] = parse_record(record.read_text(encoding="utf-8"))
        journal = scratch / JOURNAL
        if journal.is_file():  # Learn's stamp lives here, not in a phase record
            contents[JOURNAL] = parse_record(journal.read_text(encoding="utf-8"))
    return derive_from_records(str(repo), exists, contents, definition)
