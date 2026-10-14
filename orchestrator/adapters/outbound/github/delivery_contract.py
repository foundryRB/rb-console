"""DeliverySource implementations: discover deliveries and derive their state.

LocalDeliverySource scans a local root (dev, tests) and reads the scratch where a
working checkout mounts it, ``.delivery/``. GitHubDeliverySource scans an org for
repos carrying a live scratch ref - the one ``delivery/<line-id>`` orphan branch a
delivery line owns (decision 0003) - fetches the records from that ref's branch
root over the GitHub API with the shared git token, and derives state from them
with the same pure function the local path uses. ``scan`` feeds the DeliveryIndex
out of band; ``state_of`` resolves a single repo (e.g. right after it is created,
before the next background scan). Neither is called on a plain read request.
"""
from __future__ import annotations

from orchestrator.domain.delivery import DEGRADED
from orchestrator.domain.model.delivery_state import DeliveryState

#: The scratch-ref namespace a delivery line occupies: exactly one
#: ``refs/heads/delivery/*`` may exist per repo (decision 0003). Its existence IS the
#: "this repo carries a live delivery" fact; discovery enumerates the namespace with one
#: matching-refs call and resolves the single ref.
REF_NAMESPACE = "delivery/"


def _anomalous(repo: str, refs: list[str]) -> DeliveryState:
    """More than one ``delivery/*`` ref: an anomaly to surface, never a state to silently
    pick from. Parked DEGRADED with every ref named, so the fleet and the cockpit read
    the condition itself rather than one arbitrarily-chosen line's records."""
    return DeliveryState(
        repo=repo,
        exists=True,
        status=DEGRADED,
        phase=None,
        next_skill=None,
        next_command=(
            "remove the extra scratch refs (exactly one delivery/* ref may exist): "
            + ", ".join(sorted(refs))
        ),
        blocked_gate=None,
        gates=(),
        records_present=(),
    )
