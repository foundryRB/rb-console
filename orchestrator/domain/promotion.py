"""Value objects for the promotion mode: a declared target and where a proven
release stands against it (REF-Promotion sections 3 to 6). All derived on read
from the app's contract, its deploy branches and the repo host: nothing here is
ever stored, so the same inputs always yield the same state.
"""
from __future__ import annotations

from orchestrator.domain.model.instantiation import Instantiation
from orchestrator.domain.model.promotion_state import PromotionState
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_position import TargetPosition


def derive_instantiation(*, has_entry_environment: bool, has_repository_target: bool) -> Instantiation:
    """The tier, from the two facts that decide it (REF-Delivery section 1, the adopt skill's
    step 3 said as code so nobody has to re-derive it by hand)."""
    if not has_entry_environment:
        return Instantiation.MANAGED
    return Instantiation.HYBRID if has_repository_target else Instantiation.COMPLETE




# The queue's order, by attention: something claiming to serve and not answering
# outranks a review someone else may be sitting on, which outranks a release that
# has simply not moved yet. CURRENT rows never enter a queue.
_ATTENTION = {
    PromotionState.UNPROVEN: 0,
    PromotionState.UNREADABLE: 1,
    PromotionState.IN_FLIGHT: 2,
    PromotionState.PENDING: 3,
    PromotionState.CURRENT: 4,
}






def derive_position(
    *,
    target: PromotionTarget,
    proven: str,
    accepted: str | None,
    door_open: str = "",
    acceptance_answers: bool | None = None,
    door_shut: str = "",
) -> TargetPosition:
    """Where one target stands.

    ``proven`` is the release the entry environment serves; ``accepted`` is what
    the target carries (None when it could not be read); ``door_open`` names a
    submitted door not yet landed; ``acceptance_answers`` is the declared signal's
    answer, or None when the target declares none or it was not read; ``door_shut``
    is the reason the door cannot be performed at all, empty when it can.

    ``door_shut`` is judged FIRST, ahead of every other rule. A surface that cannot
    open the door cannot read the target through it either, so every later input
    would be an absence produced by the same cause, and reporting the target's
    version comparison over a door that cannot be performed states a promotion as
    the next act when no promotion is possible. The reason is the SURFACE's to
    supply, because the surfaces answer it differently and truthfully: the console
    asks the platform's own credential store, a desk asks whether its authenticated
    client reaches the pair at all. What is shared - and what the fixture corpus
    pins - is the state it derives to, the sentence it composes, and the fact that
    it outranks the rest.

    A door in flight outranks the version comparison: something is already moving,
    and a second promotion is not the next act. Acceptance is judged only where the
    target declares one, so a target closing at deployed is never reported unproven
    for a probe it never promised.
    """
    if door_shut:
        return TargetPosition(
            target=target,
            state=PromotionState.UNREADABLE,
            door_shut=True,
            detail=f"the door cannot be opened: {door_shut}",
        )
    if accepted is None:
        return TargetPosition(
            target=target,
            state=PromotionState.UNREADABLE,
            door_ref=door_open,
            detail="the target's state could not be read",
        )
    if door_open:
        return TargetPosition(
            target=target,
            state=PromotionState.IN_FLIGHT,
            accepted=accepted,
            door_ref=door_open,
        )
    if accepted and accepted == proven:
        if target.acceptance == "none":
            return TargetPosition(target=target, state=PromotionState.CURRENT, accepted=accepted)
        if acceptance_answers is False:
            return TargetPosition(
                target=target,
                state=PromotionState.UNPROVEN,
                accepted=accepted,
                detail=f"serves {accepted}, and its declared {target.acceptance} does not answer",
            )
        if acceptance_answers is None:
            # It declared a signal and the signal could not be read: unchecked is
            # not proven, and reporting it current would claim what nothing saw.
            return TargetPosition(
                target=target,
                state=PromotionState.UNREADABLE,
                accepted=accepted,
                detail=f"serves {accepted}, and its declared {target.acceptance} could not be read",
            )
        return TargetPosition(target=target, state=PromotionState.CURRENT, accepted=accepted)
    return TargetPosition(target=target, state=PromotionState.PENDING, accepted=accepted)


def attention_order(positions: list[TargetPosition]) -> list[TargetPosition]:
    """The queue: every position that wants attention, ordered by what it wants.

    CURRENT rows are dropped - a target carrying the proven release is not work -
    and the rest sort by attention, ties broken by target name so the queue is
    stable across reads.
    """
    return sorted(
        (p for p in positions if p.state is not PromotionState.CURRENT),
        key=lambda p: (_ATTENTION[p.state], p.target.name),
    )
