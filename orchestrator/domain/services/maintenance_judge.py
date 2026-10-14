"""The one-shot merge gate (INT-FC-R65), the sibling of the delivery judge: classify
a finished one-shot maintenance run into exactly one deterministic act. The review
earns the act; the ENGINE performs it - never a worker, so no agent ever merges and
no write credential ever rides a pod for merging. Total over its inputs, fail-closed:
only a recorded fresh-eyes PASS with green checks merges; everything else parks for
the operator.
"""

from __future__ import annotations

from orchestrator.domain.maintenance import CHECKS_GREEN, VERDICT_PASS
from orchestrator.domain.model.merge_gate import MergeGate
from orchestrator.domain.model.resolve_retry import ResolveRetry


def judge_one_shot(verdict: str, checks: str) -> MergeGate:
    """Map (verdict, checks) to exactly one act. A FAIL, an UNRECORDED or missing
    verdict, a red check, a pending check, or an unreadable checks state all PARK: a red
    CI blocks the merge whatever the verdict says (REF-Maintenance section 5), an
    UNRECORDED review awaits an independent reviewer, and unknown is treated as red,
    never as green."""
    if verdict == VERDICT_PASS and checks == CHECKS_GREEN:
        return MergeGate.MERGE
    return MergeGate.PARK


#: The bound on one-shot self-correction: how many resolve attempts a single ticket may
#: have (the initial drive is attempt 1 and its one fix round, REF-Maintenance section 5,
#: attempt 2) before a still-failing review degrades to the operator instead of re-driving
#: again. Keeps a genuinely unresolvable ticket - one no ticket-sized change can pass
#: review, e.g. a delivery-sized ask - from looping forever.
MAX_RESOLVE_ATTEMPTS = 2




def judge_resolve_fail(
    attempts: int, max_attempts: int = MAX_RESOLVE_ATTEMPTS
) -> ResolveRetry:
    """On a recorded one-shot ``VERDICT: FAIL``, decide between re-driving the resolve
    with the reviewer's findings as the work order (attempts remain) and degrading to the
    operator (the budget is spent). ``attempts`` is how many resolve runs the ticket has
    already had - derived by counting them on the executor, so it survives a pod restart.
    Bounded, because a ticket no ticket-sized change can resolve must reach a human, not
    loop: the sibling of the delivery retry budget (INT-FC-R19)."""
    return ResolveRetry.RETRY if attempts < max_attempts else ResolveRetry.DEGRADE
