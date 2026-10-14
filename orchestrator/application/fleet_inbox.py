"""The fleet inbox: the console's rendering of REF-Maintenance section 7's attention queue.

The queue's rules - the six signals and their order, the two folds that make one concern
read as one row, the issue stages and the act each implies, the exclusions - live in the
playbook and are derived by its `maintenance-inbox` sweep, vendored beside this package
(`orchestrator/vendor/sweep.py`, pinned in `devops/vendor/PINNED.json`). This module is the
ADAPTER: it maps the console's typed positions into the shape that derivation reads, and
its rows back into `InboxItem`. It decides nothing about the queue.

That split is the point. The skill promised "any frontend rendering the same queue derives
it the same way" and nothing enforced it, so a second implementation here could grow rules
the corpus never stated, and no test anywhere would catch the two disagreeing about the
same repo (universal violation 1: never duplicate with intent to maintain in parallel).
Archived repos never appear in any signal; a tombstone's open issues are noise by
definition.
"""

from __future__ import annotations

from dataclasses import asdict

from orchestrator.domain.model.inbox_item import InboxItem
from orchestrator.domain.model.maintenance_positions import MaintenancePositions
from orchestrator.vendor import sweep


def _position(pos: MaintenancePositions, promotion: list[dict] | None = None) -> dict:
    """One repo's typed position in the vocabulary the sweep reads.

    The two vocabularies already agree on the words that matter - a verdict is
    pass/fail/unrecorded/awaiting and checks are green/red/pending/unknown on both sides - so this is
    a rename, never a translation. A field the sweep does not read is simply not passed.
    """
    return {
        "repo": pos.repo,
        "issues": [
            {
                "number": i.number,
                "title": i.title,
                "labels": list(i.labels),
                "created_at": i.created_at,
            }
            for i in pos.issues
        ],
        "prs": [
            {
                "number": p.number,
                "title": p.title,
                "head": p.head,
                "body": p.body,
                "checks": p.checks,
                "verdict": p.verdict,
                "updated_at": p.updated_at,
            }
            for p in pos.prs
        ],
        "train": {
            "checks": pos.train.checks,
            "version": pos.train.version,
            "healthy": pos.train.healthy,
            "deployed": pos.train.deployed,
            "next_version": pos.train.next_version,
            "unreleased_total": pos.train.unreleased_total,
        },
        # The declared targets and where each stands. Absent for a repo with no
        # contract, which derives exactly the queue it always did.
        "promotion": promotion or [],
    }


def derive_inbox(
    positions: list[MaintenancePositions],
    archived: set[str] | None = None,
    running: dict[str, list[dict]] | None = None,
    promotion: dict[str, list[dict]] | None = None,
    hidden_repos: set[str] | None = None,
) -> list[InboxItem]:
    """The org queue, most urgent first.

    ``running`` is the console's own map of work in flight (``{repo: [{"act", "ticket"}]}``),
    read off the live maintenance Workflows. The sweep takes it as a flat list because its
    source differs by reader - a workflow engine here, a desk's live agent sessions there,
    nothing at all in a plain session - and it is always SUPPLIED, never discovered: a
    derivation that went looking for work in flight would be inventing state.

    ``hidden_repos`` carries the ``foundry-hidden`` TOPIC, the repo-scope twin of the label.
    It reaches the sweep rather than being applied to the result afterwards, because the mark
    covers EVERY signal a held repo raises, red CI and unshipped releases included, and a rule
    re-stated at the caller is a rule that drifts from the corpus that defines it.
    """
    jobs = [
        {"repo": repo, "act": job.get("act") or "resolve", "number": job.get("ticket")}
        for repo, active in (running or {}).items()
        for job in active
    ]
    rows = sweep.derive_inbox(
        [_position(p, (promotion or {}).get(p.repo)) for p in positions or []],
        archived=archived,
        running=jobs,
        hidden_repos=hidden_repos,
    )
    return [
        InboxItem(
            repo=row["repo"],
            signal=row["signal"],
            detail=row["detail"],
            act=row["act"],
            number=row["number"],
            ts=row["ts"],
            hidden=row["hidden"],
            stage=row["stage"],
        )
        for row in rows
    ]


__all__ = ["InboxItem", "asdict", "derive_inbox"]
