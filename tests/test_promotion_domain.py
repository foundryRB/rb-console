"""The promotion mode's pure derivations: where one declared target stands
(REF-Promotion section 6), and the attention order of the queue."""
from orchestrator.domain.model.promotion_state import PromotionState
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.promotion import attention_order, derive_position


def _env_target(name: str = "example-prod", acceptance: str = "probe") -> PromotionTarget:
    return PromotionTarget(
        name=name,
        kind=TargetKind.ENVIRONMENT,
        door="commit",
        terms="version",
        acceptance=acceptance,
        install="example",
        environment="prod",
    )


def _pair_target(name: str = "partner") -> PromotionTarget:
    return PromotionTarget(
        name=name,
        kind=TargetKind.REPOSITORY,
        door="pull-request",
        terms="source",
        acceptance="none",
        repo="their-org/their-repo",
        branch="main",
    )


class TestDerivePosition:
    def test_a_target_carrying_the_proven_release_is_current(self) -> None:
        position = derive_position(
            target=_env_target(), proven="1.42.0", accepted="1.42.0", acceptance_answers=True
        )
        assert position.state is PromotionState.CURRENT
        assert not position.behind

    def test_a_target_behind_the_proven_release_is_pending(self) -> None:
        position = derive_position(target=_env_target(), proven="1.42.0", accepted="1.39.2")
        assert position.state is PromotionState.PENDING
        assert position.accepted == "1.39.2"

    def test_a_submitted_door_outranks_the_version_comparison(self) -> None:
        # Something is already moving; a second promotion is not the next act.
        position = derive_position(
            target=_pair_target(), proven="1.42.0", accepted="1.36.0", door_open="PR 14"
        )
        assert position.state is PromotionState.IN_FLIGHT
        assert position.door_ref == "PR 14"

    def test_serving_the_release_while_acceptance_is_silent_is_unproven(self) -> None:
        position = derive_position(
            target=_env_target(), proven="1.42.0", accepted="1.42.0", acceptance_answers=False
        )
        assert position.state is PromotionState.UNPROVEN
        assert "does not answer" in position.detail

    def test_a_target_declaring_no_acceptance_closes_at_deployed(self) -> None:
        # It never promised a signal, so its silence is not a failure to answer.
        position = derive_position(
            target=_env_target(acceptance="none"),
            proven="1.42.0",
            accepted="1.42.0",
            acceptance_answers=False,
        )
        assert position.state is PromotionState.CURRENT

    def test_a_declared_signal_that_cannot_be_read_is_not_current(self) -> None:
        # Unchecked is not proven: reporting current would claim what nothing saw.
        position = derive_position(
            target=_env_target(), proven="1.42.0", accepted="1.42.0", acceptance_answers=None
        )
        assert position.state is PromotionState.UNREADABLE
        assert "could not be read" in position.detail

    def test_an_unreadable_target_is_never_guessed(self) -> None:
        position = derive_position(target=_env_target(), proven="1.42.0", accepted=None)
        assert position.state is PromotionState.UNREADABLE
        assert position.accepted == ""


class TestAttentionOrder:
    def test_current_rows_are_not_work(self) -> None:
        current = derive_position(
            target=_env_target(), proven="1.0.0", accepted="1.0.0", acceptance_answers=True
        )
        assert attention_order([current]) == []

    def test_unproven_outranks_in_flight_outranks_pending(self) -> None:
        pending = derive_position(target=_env_target("a-pending"), proven="2.0.0", accepted="1.0.0")
        in_flight = derive_position(
            target=_pair_target("b-flight"), proven="2.0.0", accepted="1.0.0", door_open="PR 3"
        )
        unproven = derive_position(
            target=_env_target("c-unproven"),
            proven="2.0.0",
            accepted="2.0.0",
            acceptance_answers=False,
        )
        queue = attention_order([pending, in_flight, unproven])
        assert [p.target.name for p in queue] == ["c-unproven", "b-flight", "a-pending"]
