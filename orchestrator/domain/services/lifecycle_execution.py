"""Select execution from a pinned lifecycle."""
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.delivery import DELIVERED
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition


def _remaining(state: DeliveryState, start: str | None = None, definition: LifecycleDefinition = CURRENT_LIFECYCLE) -> list:
    phases = definition.phases
    names = [p.name for p in phases]
    phase = start or state.phase
    if phase in names:
        remaining = list(phases[names.index(phase):])
    else:
        remaining = list(phases)
    # A delivered run performs the journal completion. Other runs finish their record gates.
    if start is None and state.status != DELIVERED or start is not None and definition.phases[names.index(start)].completion != "journal":
        remaining = [p for p in remaining if p.completion != "journal"]
    return remaining


def _adopted_studios(start_name: str | None, definition: LifecycleDefinition = CURRENT_LIFECYCLE) -> tuple[str, ...]:
    names = [p.name for p in definition.phases]
    if start_name not in names:
        return ()
    return tuple(dict.fromkeys(p.studio for p in definition.phases[:names.index(start_name)] if p.studio))
