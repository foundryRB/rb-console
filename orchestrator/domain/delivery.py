"""Domain model for a delivery's derived state.

Progress is never stored; it is DERIVED from which committed records exist in the
line's scratch and whether each phase's gate is signed (a dated stamp) or pending.
The scratch lives on the repo's one ``delivery/<line-id>`` orphan branch, records at
the branch root (decision 0003); a working checkout mounts that branch at
``.delivery/`` as a linked worktree, which is where every on-disk path below points.
This module exposes lifecycle-derived names and delivery identity helpers.
Value objects live in domain/model and resolution in domain/services/delivery_resolution.py.
"""
from __future__ import annotations

import re

from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE

#: The scratch's mount point in a working checkout: a linked worktree of the line's own
#: ``delivery/<line-id>`` scratch ref, git-ignored on the default branch (REF-Delivery,
#: decision 0003). Paths under this constant are the on-disk contract; WHICH ref backs
#: them is resolved per repo (``DeliveryState.scratch_ref``), never a constant.
SCRATCH = ".delivery"

#: The journal inside the scratch: Learn's running record. Never a phase record (its
#: presence advances nothing), but its leading frontmatter carries ``learned: <date>``
#: once reconcile-delivery has executed, so a finished Learn is derivable like every
#: other phase even though Learn leaves no record of its own.
JOURNAL = "journal.md"


def delivery_slug(repo: str) -> str:
    """The delivery slug that threads through every studio: the repo's last path segment
    (``org/name`` -> ``name``, ``path\\to\\name`` -> ``name``), matching each studio's
    project/app key convention. ONE definition, so the cockpit's studio matching and the
    worker's launch prompt pin the exact same key - a studio project keyed by any other
    name (a prettier hyphenation, say) orphans from its delivery and cannot be linked back.
    """
    if not repo:
        return repo
    return repo.replace("\\", "/").rstrip("/").split("/")[-1]


def same_repository(a: str, b: str) -> bool:
    """Whether two ``owner/name`` identities name one repository. GitHub resolves both
    parts case-insensitively, and the console holds the identity in both forms: a command's
    context lowercases it, while an execution's annotation keeps the case it was created
    with (INT-FC-R180)."""
    return a.lower() == b.lower()


def studio_project_key(studio: str, slug: str) -> str:
    """The key a delivery-side studio holds the delivery's project under, by that studio's own
    naming rule: estimatekit keeps the delivery slug verbatim, and protopane derives a project's
    key from its name, lower-cased with each run of other characters a hyphen (`SolveOS` is
    `solveos` there). One definition, so the worker's prompt, the gate export and the cockpit
    name the same project before and after the phase creates it."""
    if studio == "protopane":
        return re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "project"
    return slug


SEQUENCE = tuple(p for p in CURRENT_LIFECYCLE.phases if p.completion == "record")
LEARN = next(p for p in CURRENT_LIFECYCLE.phases if p.completion == "journal")

#: The catalog's outsider: the agent the maintenance loop's review act is handed to, and never
#: a phase worker. A delivery gate binds no reviewer - its review is the phase's own, the
#: adversarial-review skill run inside the phase, and the entrypoint only locates the
#: artifact it left (decision 0005).
REVIEW_AGENT = "reviewer"

#: The playbook studio's MCP door. Workers read skills from their pinned local tree.
PLAYBOOK_STUDIO = "playbook-studio"

#: Which MCP studio each phase drives, derived from the line - the single source of
#: truth for the phase->studio map (the compiler's launch and the cross-studio view
#: both consume the generated lifecycle). The intent+plan phase has no door (CSD is
#: applied locally), so it is absent here.
STUDIO_BY_PHASE: dict[str, str] = {p.name: p.studio for p in (*SEQUENCE, LEARN) if p.studio}




# Status values a DeliveryState can carry.
NOT_A_DELIVERY = "not-a-delivery"  # no scratch (no delivery/* ref; locally no .delivery/): a bare repo
RUN_PHASE = "run-phase"            # the next phase's record is missing; run it
AWAITING_GATE = "awaiting-gate"    # a phase is done but its gate is unsigned; suspend
DELIVERED = "delivered"            # all four gates signed; ready for learn/reconcile
LEARNED = "learned"                # learn ran (journal stamped learned:); close the line
DEGRADED = "degraded"              # a phase record did not finish (aborted, or left in-progress); parked for a human




SEED_NEW = "new"              # no delivered tag, no seed tag: the line grows from an ask
#: Where a recast's source app lives: under this folder on the line's own orphan scratch
#: ref (``.delivery/_recast/`` in a mounted worktree). The recast source is retained by
#: the annotated seed tag and the delivered tag when the line closes (REF-Recast section 2).
RECAST_DIR = "_recast"

SEED_FOLLOW_ON = "follow-on"  # a delivered/<slug>/P<n> tag: a shipped phase is under it
SEED_RECAST = "recast"        # a seed/<slug> tag: an existing app was seeded into the repo
SEED_DEMO = "demo"            # a demo-<x> repo over a line <x> the org holds: a rehearsal (REF-Demo)

#: The name prefix a demo line carries (REF-Demo section 2): ``demo-<x>`` rehearses ``<x>``.
DEMO_PREFIX = "demo-"


def demo_source_name(repo: str) -> str:
    """The source a demo-named repo points at, or '' when the name carries no prefix: a repo
    named ``demo-<x>`` (an ``owner/`` in front is dropped) names ``<x>``. Read off the name
    alone; whether ``<x>`` is a line the org holds is the source's read, and only that read
    makes the line a demo (derive_seed takes its answer as ``demo_source``)."""
    name = repo.split("/")[-1].strip()
    if not name.startswith(DEMO_PREFIX):
        return ""
    return name[len(DEMO_PREFIX):]


def derive_seed(*, has_delivered_tag: bool, has_seed_tag: bool, demo_source: str = "") -> str:
    """What a line starts from, from the two tags that settle it (REF-Delivery section 1,
    "What the line starts from") and, for a demo, the source the org holds. A demo wins: a
    ``demo-<x>`` repo whose ``<x>`` is a line is a rehearsal whatever its own tags say, since
    a demo that shipped once and is run again is still a rehearsal, never a follow-on. Then
    a delivered tag wins: a repo that shipped a phase is a follow-on whatever else it holds,
    and the recast doctrine applies beside it."""
    if demo_source:
        return SEED_DEMO
    if has_delivered_tag:
        return SEED_FOLLOW_ON
    if has_seed_tag:
        return SEED_RECAST
    return SEED_NEW
