"""Where a target stands, held to the playbook's own corpus.

The promote skill states the rule this suite exists to keep: "a surface that re-derives
promotion state runs every case, and a rule read differently there than here fails a test
rather than shipping two views that disagree about the same target." The desk has run the
corpus since the dock was built. This console re-derived the same positions in Python and
ran NONE of it - so the one mechanism holding two runtimes to one doctrine was, for one of
those runtimes, a comment.

Nothing here re-states a rule. The corpus is vendored beside the inbox sweep's
(``orchestrator/vendor/promote/``, pinned in ``devops/vendor/PINNED.json``) and this file is
only the adapter: the corpus's own field names in, this repo's value objects out.

Audit: csd-intent .
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_intent import intent

from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.promotion import attention_order, derive_position

_FIXTURES = Path(__file__).resolve().parents[1] / "orchestrator" / "vendor" / "promote" / "fixtures"
_CASES = sorted(_FIXTURES.glob("*.json"))


def _target(spec: dict) -> PromotionTarget:
    """A corpus target in THIS repo's vocabulary. The corpus states the contract's own field
    names (``probe``, ``suite_pass``); the console carries the same facts under its own, and
    fills what a case leaves out - which is all an adapter is for."""
    return PromotionTarget(
        name=spec.get("name", ""),
        kind=TargetKind(spec.get("kind", "environment")),
        door=spec.get("door", ""),
        terms=spec.get("terms", ""),
        acceptance=spec.get("acceptance", "none"),
        install=spec.get("install", ""),
        environment=spec.get("environment", ""),
        repo=spec.get("repo", ""),
        branch=spec.get("branch", ""),
        credential=spec.get("credential", ""),
        probe_url=spec.get("probe", ""),
        suite_url=spec.get("suite", ""),
        suite_pass=spec.get("suite_pass", ""),
    )


def _positions(case: dict) -> list:
    return [
        derive_position(
            target=_target(entry["target"]),
            proven=case["input"]["proven"],
            accepted=entry["accepted"],
            door_open=entry.get("door_open", "") or "",
            acceptance_answers=entry.get("acceptance_answers"),
            door_shut=entry.get("door_shut", "") or "",
        )
        for entry in case["input"]["targets"]
    ]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _CASES, ids=lambda p: p.stem)
@intent("INT-FC-R133")
def test_a_targets_position_matches_the_corpus(path: Path) -> None:
    case = _load(path)
    derived = [
        {
            "name": p.target.name,
            "state": p.state.value,
            "accepted": p.accepted,
            "door_ref": p.door_ref,
            "detail": p.detail,
        }
        for p in _positions(case)
    ]
    assert derived == case["expected"]["positions"], case["why"]


@pytest.mark.parametrize("path", _CASES, ids=lambda p: p.stem)
@intent("INT-FC-R133")
def test_the_queues_order_matches_the_corpus(path: Path) -> None:
    case = _load(path)
    queue = [p.target.name for p in attention_order(_positions(case))]
    assert queue == case["expected"]["queue"], case["why"]


@intent("INT-FC-R133")
def test_every_case_in_the_corpus_runs_so_a_thin_run_cannot_pass_for_a_full_one() -> None:
    """A vendored subset would agree with this console by construction and with nothing else.
    The names are asserted rather than a count, because a count is what lets a refresh
    silently drop the case carrying most of the contract while the suite still reports green.
    """
    names = {p.stem for p in _CASES}
    for required in (
        "attention-order",
        "door-shut-outranks-every-other-rule",
        "in-flight-outranks-the-version",
        "no-targets-declared",
        "pending-when-proven-is-ahead",
        "unchecked-is-not-proven",
        "unproven-when-the-signal-says-no",
        "unreadable-is-not-current",
    ):
        assert required in names, f"the vendored corpus lost its {required} case"
