"""Open or advance a delivery record's frontmatter: the deterministic writer of the
REF-Delivery record block, so no agent hand-writes frontmatter (section 1).

The phase authors the record's BODY (the prose is the phase's to write); this helper
owns the frontmatter block. Run it to open a record (`--status in-progress`) and
again when the phase's work is authored and the gate is reached (`--status gate`,
the default), which leaves `signed: pending` for the gate helper (stamp_gate.py,
this folder) to close over the recorded review. Design's close_gate.py composes
this same block for its own record; every other record gets it from here.

It initializes `signed:` to `pending` on a record that has no signature and refuses
to rewrite the block of a record whose gate is already signed: a closed gate is
history, not a template. Provenance fields it is not handed (`run`, `attempt`,
`credential_ref`, `started`) carry over from the existing block when present, so
re-running it never erases them.

`mode`, `finished`, and `reviewed` describe the current attempt rather than the
record's history (REF-Delivery.md section 1 holds the rule; this is how it is
applied). `--mode` is passed on a re-drive that changed mode, and `--finished`
records an end this helper is told. Opening a record for work (`--status
in-progress`) clears `finished` and `reviewed` both: a phase that is running has
not ended, and a review is evidence about one attempt's document, which a re-drive
by definition replaces - carried, a `reviewed:` date lets the stamp close the new
attempt's gate over the old attempt's review. The gate helper (stamp_gate.py)
records the review and fills an empty `finished` at the signature. A `finished`
earlier than `started` is reported. `signed_at` and `outcome`, the closure fields
the stamp writes beside `signed:`, are never carried: this helper runs only on an
open gate, so a pair it meets describes a closure that is gone.

`onboarding_pr` (REF-Delivery.md section 5b) is `--onboarding-pr`, repeatable, and
`attests` - the default-branch commit this attempt's evidence chain verified live,
cleared at the reopen like `finished` and `reviewed` - is `--attests`, so every field
the build phase is told to record is one this helper can write and no phase reaches
for the frontmatter by hand (anti-pattern 30). `claims_attested` and `claims_total`,
the exit check's passing attestation audit (what the delivery analytics read as
claims attested), are `--claims-attested` and `--claims-total`: one measurement in
two numbers, so both flags or neither, non-negative, attested no greater than total,
and current-attempt evidence like `attests` (a later audit in the same attempt
replaces them; the reopen clears them). Recording evidence is not a phase
transition: with `--status` omitted and an evidence flag present, the record's
current status carries - the bare invocation's `gate` default is a gate-reached
declaration, and a grant recorded mid-run must not make one.

`delivers` (REF-Delivery.md section 1, "Phased delivery") is `--delivers`: the scope
phase's pin of the one estimation phase this line delivers, the field the proposal
gate export refuses a record without. Scope-owned line provenance, never attempt
evidence - a re-drive delivers the same phase - so nothing clears it, and an absent
flag carries the recorded value. A field a reader refuses on must be one this helper
can write: a real line reached a green, reviewed proposal gate that no tool could
sign, the pin hand-writable only (playbook#182).

`surface` (REF-Delivery.md section 1, section 3) is `--surface`: the scope phase's
declaration of the increment's surface, `surfaced` (a human surface, whatever the
tool that prototypes it) or `none` (a service, a worker, a proxy: no human surface,
the docs site its only DOM), read by the design phase and the plan. Scope-owned line
provenance like `delivers`: nothing clears it, and an absent flag carries the
recorded value.

`slug` (REF-FollowOn.md section 5) is `--slug`: the verbatim delivery-side
studio linkage key. Scope-owned line provenance like `delivers` and `surface`,
it survives reopens and attempt bumps. A recorded key accepts only the same value.
Pass one flat identifier made of letters,
digits, dots, underscores or hyphens, beginning with a letter or digit.

`--attests` is corroborated against git before it is written, at the door, because
the recording tree is the only place a narrated-but-unshipped commit is visible at
all (a retry re-clones, and a fresh clone can never see what was never pushed): the
SHA must resolve, a remote branch must hold it, and HEAD must carry no commit that
no remote holds. The corroboration makes no assumption about merge topology -
squash, rebase, and a default branch moved past the attested commit all pass; a
team's merge strategy is its own. `--attests-repo` points the corroboration at the
checkout the evidence actually ran against when that is not `--repo` (a Managed
line's home checkout); a directory that is not a git work tree notes and records
uncorroborated.

Stdlib only. Usage:

    # open the record when the phase starts
    python reach_gate.py --repo <repo-root> --record proposal.md \
        --phase scope --skill deliver-engagement --gate proposal --status in-progress

    # mark the gate reached once the work is authored (before the fresh-eyes review)
    python reach_gate.py --repo <repo-root> --record proposal.md \
        --phase scope --skill deliver-engagement --gate proposal

    # record an onboarding pull request as its grant lands, mid-run
    python reach_gate.py --repo <repo-root> --record build.md \
        --phase build+ship --skill run-delivery-plan --gate delivery \
        --status in-progress \
        --onboarding-pr https://github.com/<org>/<platform-repo>/pull/109
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCRATCH = ".delivery"
_STATUSES = ("in-progress", "gate", "aborted")


def _front_end(lines: list[str]) -> int | None:
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return None


def _existing(lines: list[str], end: int) -> dict[str, str]:
    fields: dict[str, str] = {}
    for i in range(1, end):
        m = re.match(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$", lines[i])
        if m:
            fields[m.group(1).lower()] = m.group(2).strip().strip('"').strip("'")
    return fields


def _stamp(value: str) -> datetime | None:
    """A record's ISO stamp as an aware datetime, or None when it cannot be read.

    A stamp carrying no zone is read as UTC, the zone every stamp this helper writes,
    so a record hand-touched into `...T23:13:59` is compared rather than raised on:
    this runs on every invocation, and a helper that raises hands the phase back the
    un-normalized frontmatter it exists to replace.
    """
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def _precedes(finished: str, started: str) -> bool:
    """True when both stamps read and the phase ends before it begins.

    A stamp this cannot read reports nothing: the check exists to warn, and a format
    it does not recognise is not evidence of an impossible timeline.
    """
    ends, begins = _stamp(finished), _stamp(started)
    return ends is not None and begins is not None and ends < begins


def _git(repo: Path, *argv: str) -> tuple[int, str]:
    """(returncode, output) of a git command in `repo`, stderr folded in on failure."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *argv], capture_output=True, text=True, encoding="utf-8"
    )
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        out = (out + " " + (proc.stderr or "").strip()).strip()
    return proc.returncode, out


def _attests_refusal(repo: Path, sha: str) -> str | None:
    """The refusal line when the repo's git state does not corroborate `attests`, or None.

    `attests` claims the evidence chain verified THIS code live, and the scratch rides
    its own ref, so the record is the only durable link from the retained evidence back
    to the code (REF-Delivery.md section 5b). The claim is checked at the one moment it
    is still checkable: in the recording tree, where a narrated-but-unshipped follow-up
    commit is visible at all - the pod's local tree dies with the pod, a retry
    re-clones, and a fresh clone can never see what was never pushed. A real build
    reached its gate narrating a post-review fix as done while the fix sat local-only
    behind an attests that did not include it, and reconcile found it by accident. Three
    reads: the SHA must resolve here, a remote branch must hold it, and HEAD must carry
    no commit that no remote holds. Deliberately nothing about ancestry or merge
    topology: squash, rebase, and a default branch moved past the attested commit are a
    team's own choices, and a first cut that policed ancestry needed a tree-equality
    escape for squash flows - an escape for a false positive the check itself created,
    the tell that it had stopped measuring durability and started grading workflow. A
    directory that is not a git work tree notes and skips: every real delivery checkout
    is one, and the field's own mechanics are attested against bare directories.
    """
    if shutil.which("git") is None:
        print("NOTE: git is not on PATH; --attests is recorded uncorroborated.")
        return None
    code, _ = _git(repo, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        print(f"NOTE: {repo} is not a git work tree; --attests is recorded uncorroborated.")
        return None
    code, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if code != 0:
        return (
            f"REFUSED: --attests {sha!r} does not resolve to a commit in {repo}; the "
            "evidence chain cannot attest code this repo does not hold. Fetch the "
            "commit, fix the SHA, or point --attests-repo at the checkout the evidence "
            "actually ran against (a Managed line's home checkout)."
        )
    code, remotes = _git(repo, "remote")
    if code != 0 or not remotes:
        return None
    code, holders = _git(repo, "branch", "-r", "--contains", sha)
    if code == 0 and not holders:
        return (
            f"REFUSED: no remote branch holds {sha[:12]}; a SHA that never reached "
            "the remote dangles for every fresh clone that reads the record "
            "(REF-Delivery.md section 5b). Push it, then re-record."
        )
    code, ahead = _git(repo, "log", "--oneline", "--max-count=10", "HEAD", "--not", "--remotes")
    if code != 0 or not ahead:
        return None
    listed = "\n  ".join(ahead.splitlines())
    return (
        "REFUSED: HEAD carries commits no remote holds:\n"
        f"  {listed}\n"
        "They exist only in this working tree, which does not outlive the run (a retry "
        "re-clones), so attesting while they sit here records evidence that does not "
        "cover what ships - a real post-review fix sat exactly here, narrated as done, "
        "found at reconcile by accident. Push them and re-verify live, then re-record - "
        "or remove them if they are not this delivery's work."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Delivery repo root (holds .delivery/)")
    parser.add_argument(
        "--record", required=True, help="Scratch record filename: proposal.md / handoff.md / build.md"
    )
    parser.add_argument("--phase", required=True, help="Phase name for the block (e.g. scope)")
    parser.add_argument("--skill", required=True, help="Skill writing the record (e.g. deliver-engagement)")
    parser.add_argument("--gate", required=True, help="Gate the record carries (e.g. proposal)")
    parser.add_argument(
        "--status",
        choices=_STATUSES,
        help="in-progress when the phase opens the record; gate when its work is authored "
        "and the gate is reached (the default for a bare invocation); aborted on an "
        "explicit give-up. Omitted while recording evidence (--onboarding-pr, "
        "--finished), the record's current status carries: recording is not a "
        "phase transition.",
    )
    parser.add_argument("--run", default="", help="Opaque run id for the frontmatter")
    parser.add_argument("--attempt", type=int, default=0, help="1-based attempt (0 keeps the existing value)")
    parser.add_argument("--mode", choices=("interactive", "one-shot"), help="Run mode for the frontmatter")
    parser.add_argument("--credential-ref", default="", help="Citation of the driving credential, never the secret")
    parser.add_argument("--started", help="ISO start timestamp (default: existing value, else now)")
    parser.add_argument(
        "--finished",
        default="",
        help="ISO end timestamp for THIS attempt. Like --mode it describes the attempt "
        "running now, so opening a record for work clears it and the gate helper fills it "
        "at the signature; pass it to record when an aborted attempt ended.",
    )
    parser.add_argument(
        "--delivers",
        default="",
        metavar="P<n>",
        help="The one estimation phase this line delivers (REF-Delivery.md section 1, "
        "'Phased delivery'), written as the scope-owned `delivers:` field the proposal "
        "gate export keys on. Single-valued line provenance: an absent flag carries the "
        "recorded value, and nothing clears it - a re-drive delivers the same phase. "
        "Uppercased on write, the shape the delivered tag spells.",
    )
    parser.add_argument(
        "--slug",
        help="Verbatim delivery-side studio linkage key (REF-FollowOn.md section 5). "
        "Scope-owned line provenance: omitted carries the recorded value; reopens and "
        "attempt bumps retain it; a recorded key accepts only the same value. "
        "Letters, digits, dots, underscores and hyphens, "
        "beginning with a letter or digit; no case or prefix normalization.",
    )
    parser.add_argument(
        "--surface",
        default="",
        metavar="surfaced|none",
        help="The increment's surface (REF-Delivery.md section 1, section 3), written as the "
        "scope-owned `surface:` field the design phase reads: `surfaced` (a human surface) "
        "or `none` (a service, a worker, a proxy: no human surface). Single-valued line "
        "provenance: an absent flag carries the recorded value, and nothing clears it. "
        "Lowercased on write.",
    )
    parser.add_argument(
        "--onboarding-pr",
        action="append",
        default=[],
        metavar="URL",
        help="URL of a platform onboarding pull request this phase opened (REF-Delivery.md "
        "section 5b), written as the run-scoped `onboarding_pr:` field. Repeatable: pass "
        "the app's grant first, since a reader that takes one takes the first.",
    )
    parser.add_argument(
        "--attests",
        default="",
        metavar="SHA",
        help="Default-branch commit THIS attempt's evidence chain verified live "
        "(REF-Delivery.md section 5b), written as the run-scoped `attests:` field. "
        "Single-valued: a later verification in the same attempt replaces the earlier "
        "one, and re-opening the record for work clears it. Corroborated against git "
        "before it is written: the SHA must resolve, a remote branch must hold it, and "
        "HEAD must carry no commit that no remote holds (merge topology is never judged).",
    )
    parser.add_argument(
        "--attests-repo",
        default="",
        metavar="PATH",
        help="The git checkout the attested SHA lives in (default: --repo). A Managed "
        "line's evidence runs against the home checkout ($FC_HOME_DIR), not the "
        "foundry-side repo holding .delivery/; point the corroboration there.",
    )
    parser.add_argument(
        "--claims-attested",
        type=int,
        default=None,
        metavar="N",
        help="Claims the exit check's passing attestation audit found attested, written as "
        "the run-scoped `claims_attested:` field the delivery analytics read. One "
        "measurement with --claims-total, so both flags or neither; current-attempt "
        "evidence like --attests: a later audit in the same attempt replaces it, and "
        "re-opening the record for work clears it.",
    )
    parser.add_argument(
        "--claims-total",
        type=int,
        default=None,
        metavar="N",
        help="Claims the same audit declared, written as `claims_total:` beside "
        "`claims_attested:`; attested is never greater than total.",
    )
    args = parser.parse_args()

    # Every field is machine-read, so a value that cannot carry its meaning is refused
    # at the door rather than written and discovered by a later reader.
    if args.finished and _stamp(args.finished) is None:
        print(f"REFUSED: --finished {args.finished!r} is not an ISO 8601 timestamp.")
        return 1
    if (args.claims_attested is None) != (args.claims_total is None):
        print(
            "REFUSED: --claims-attested and --claims-total are one measurement in two "
            "numbers; pass both or neither, so the record never carries a count with no total."
        )
        return 1
    if args.claims_attested is not None and (
        args.claims_attested < 0 or args.claims_total < 0 or args.claims_attested > args.claims_total
    ):
        print(
            f"REFUSED: claims_attested {args.claims_attested} of claims_total {args.claims_total} "
            "cannot be true; both are non-negative and attested is never greater than total."
        )
        return 1
    for url in args.onboarding_pr:
        if len(url.split()) != 1 or not re.match(r"https?://", url):
            print(
                f"REFUSED: --onboarding-pr {url!r} is not a single http(s) URL; the field "
                "records the grants space-separated, one URL per flag, and what it holds "
                "is linked by readers, so only a URL can carry the meaning."
            )
            return 1
    if args.delivers and not re.fullmatch(r"[Pp]\d+", args.delivers):
        print(
            f"REFUSED: --delivers {args.delivers!r} is not a phase pin (P<n>); the field "
            "names the one estimation phase this line delivers, and the proposal gate "
            "export keys on exactly that shape (REF-Delivery.md section 1)."
        )
        return 1
    if args.slug is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.slug):
        print(f"REFUSED: --slug {args.slug!r} is not a single flat linkage identifier.")
        return 1
    if args.surface and args.surface.strip().lower() not in ("surfaced", "none"):
        print(
            f"REFUSED: --surface {args.surface!r} is outside the vocabulary; the field is "
            "machine-read by the design phase, so it carries exactly `surfaced` or `none` "
            "(REF-Delivery.md section 1). Nothing is recorded."
        )
        return 1
    if args.attests and not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.attests):
        print(
            f"REFUSED: --attests {args.attests!r} is not a commit SHA (7-40 hex chars); "
            "the field pins which code the evidence attests, and only a SHA carries that."
        )
        return 1
    if args.attests:
        corroboration = _attests_refusal(Path(args.attests_repo or args.repo), args.attests)
        if corroboration:
            print(corroboration)
            return 1

    scratch = Path(args.repo) / _SCRATCH
    record = scratch / args.record
    body = ""
    carried: dict[str, str] = {}
    if record.is_file():
        lines = record.read_text(encoding="utf-8").splitlines(keepends=True)
        end = _front_end(lines)
        if end is not None:
            carried = _existing(lines, end)
            if _DATE.match(carried.get("signed", "")):
                print(
                    f"REFUSED: {args.record} gate is already signed ({carried['signed']}); "
                    "a closed gate's record is history, not a template."
                )
                return 1
            body = "".join(lines[end + 1 :])
        else:
            body = "".join(lines)

    if args.slug is not None and carried.get("slug") and args.slug != carried["slug"]:
        print("REFUSED: --slug differs from the recorded linkage key; REF-FollowOn "
              "section 5 requires its verbatim spelling.")
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # A record's own `attempt` is read once, and a value that is not a 1-based number is
    # UNKNOWN rather than zero. Both other readings destroy something: raising leaves the
    # record un-normalized (anti-pattern 30), and treating it as zero reads every such
    # record as a bump, which clears the end stamp of a record whose provenance is merely
    # malformed. Unknown provenance is not evidence that this attempt is a new one.
    raw_attempt = carried.get("attempt", "")
    try:
        prior = int(raw_attempt) if raw_attempt else 1
    except ValueError:
        prior = None
    if prior is not None and prior < 1:
        prior = None
    attempt = args.attempt if args.attempt > 0 else (prior or 1)
    bumped = prior is not None and attempt > prior
    if prior is None:
        print(
            f"NOTE: `attempt: {raw_attempt}` is not a 1-based attempt number; it is "
            f"recorded as {attempt} for this attempt."
        )
    # An invocation that only records evidence is not a phase transition. The bare
    # default (`gate`) is the gate-reached declaration the skill invocations rely on,
    # but recording a grant mid-run (the build's step 3) must not flip an in-progress
    # record to `gate`: the worker stamps, advances, and stages on that value, so a
    # build that dies after onboarding but before verified-live would read as
    # gate-reached instead of retried. With --status omitted and evidence flags
    # present, the record's own status carries.
    if args.status:
        status = args.status
    elif (
        args.onboarding_pr
        or args.finished
        or args.attests
        or args.delivers
        or args.surface
        or args.slug is not None
        or args.claims_attested is not None
    ) and carried.get("status"):
        status = carried["status"]
    else:
        status = "gate"
    mode = args.mode or carried.get("mode") or "interactive"
    # `mode` describes the CURRENT attempt, not the record's history (REF-Delivery.md
    # section 1). Carrying it over is right for provenance and wrong the moment the mode
    # itself changed between attempts: a re-drive under a different mode inherits a lie,
    # which is how a record came to read `mode: interactive` over a body narrating an
    # unattended one-shot run.
    if args.mode is None and carried.get("mode") and bumped:
        print(
            f"NOTE: attempt {attempt} carried `mode: {mode}` over from attempt "
            f"{carried.get('attempt')}. If this attempt runs in the other mode, pass "
            "--mode explicitly; `mode` describes the current attempt."
        )
    started = args.started or carried.get("started") or now
    # `reviewed` is evidence about the CURRENT attempt's document, never the line's
    # provenance: a re-drive produces a different document, and the stamp treats a
    # dated `reviewed:` as sufficient evidence, so a carried date closes the new
    # attempt's gate over the old attempt's review - a real record handed its signer
    # exactly that stamp command, and fresh eyes caught what the tooling did not.
    # Cleared by the same signals that clear `finished`; an evidence-only call and a
    # same-attempt gate-reach keep it, so the record-review-then-stamp rhythm is
    # untouched. The clearing signal is the EXPLICIT `--status in-progress` (or a
    # bump), never the resolved status: an evidence-only call inherits the record's
    # status, and a clear keyed on the inherited value would let recording one piece
    # of evidence erase another - the current-attempt fields' designed home is the
    # open record, so a call that names no phase transition mutates nothing beyond
    # the field it names.
    reopened = args.status == "in-progress"
    reviewed = "" if (bumped or reopened) else carried.get("reviewed", "")
    # `finished` is the other current-attempt field, and the signal that clears it is the
    # one every phase actually sends: `--status in-progress`, the record being opened for
    # work. A phase that is running has not ended, and stamp_gate.py fills an empty field
    # at the signature, so the ordinary path stays untouched. Carrying it instead makes
    # the field unwritable for the rest of the line: the stamp declines to overwrite a
    # value already there, and hand-editing frontmatter is anti-pattern 30, so one stale
    # stamp survives to the signature (a real record closed 14 attempts reading
    # `finished:` two weeks before its own `started:`). An explicit attempt bump clears it
    # too, for a caller that hands its own numbering in.
    if args.finished:
        finished = args.finished
    elif bumped or reopened:
        finished = ""
    else:
        finished = carried.get("finished", "")
    if finished and _precedes(finished, started):
        print(
            f"NOTE: `finished: {finished}` precedes `started: {started}`, so this record "
            "dates its end before its beginning. Pass --finished with this attempt's end, "
            "or leave it for the gate helper to fill at the signature."
        )
    # Every URL recorded STAYS recorded. The onboarding sequence opens its grants one at
    # a time and records each as it lands (run-delivery-plan step 3), so an invocation
    # carrying one flag adds to the field rather than replacing it: replacing would drop
    # the app's grant the moment the database's was recorded, which is the loss this
    # field exists to end. Space-separated on one line keeps the block flat key/value
    # (REF-Delivery.md section 1), and a reader that takes a single token takes the
    # first, which is the app's grant because that is the order the sequence runs.
    onboarding_pr = " ".join(
        dict.fromkeys(carried.get("onboarding_pr", "").split() + args.onboarding_pr)
    )
    # `attests` pins which default-branch commit THIS attempt's evidence chain verified
    # live (REF-Delivery.md section 5b): the scratch rides its own ref, so the record is
    # the only durable link from the retained evidence back to the code. A re-drive
    # verifies different code, so the reopen clears it with `finished` and `reviewed`;
    # within one attempt a later verification replaces the earlier one. Lowercased on
    # write, the shape every git SHA reader emits and compares.
    if args.attests:
        attests = args.attests.lower()
    elif bumped or reopened:
        attests = ""
    else:
        attests = carried.get("attests", "")
    # `claims_attested` / `claims_total` record the exit check's passing attestation
    # audit, the fourth current-attempt evidence pair: a re-drive re-audits, so the reopen
    # clears them with `attests`, and within one attempt the latest audit is the count.
    # Read by the delivery analytics off this block, which is why the exit check writes
    # them through this helper rather than narrating them (anti-pattern 30).
    if args.claims_attested is not None:
        claims_attested, claims_total = str(args.claims_attested), str(args.claims_total)
    elif bumped or reopened:
        claims_attested, claims_total = "", ""
    else:
        claims_attested = carried.get("claims_attested", "")
        claims_total = carried.get("claims_total", "")
    # `delivers` pins the one estimation phase this line delivers (REF-Delivery.md
    # section 1, "Phased delivery"): scope-owned line provenance, never current-attempt
    # evidence, so neither the reopen nor an attempt bump clears it - a re-drive
    # delivers the same phase. Only the flag's value is normalized (uppercased, the
    # spelling the delivered tag uses); a value the record already carries is carried
    # untouched, because an identifier a record holds outranks a document's example of
    # it (REF-Delivery.md section 1).
    delivers = args.delivers.upper() if args.delivers else carried.get("delivers", "")
    # `surface` is scope's declaration of the increment's shape (REF-Delivery.md section
    # 1, section 3), read by the design phase: line provenance like `delivers`, so
    # nothing clears it; only the flag's value is normalized (lowercased).
    surface = args.surface.strip().lower() if args.surface else carried.get("surface", "")
    # The delivery-side studio linkage is verbatim scope-owned provenance.
    slug = args.slug if args.slug is not None else carried.get("slug", "")
    front = (
        "---\n"
        f"phase: {args.phase}\n"
        f"skill: {args.skill}\n"
        f"status: {status}\n"
        f"gate: {args.gate}\n"
        f"signed: {carried.get('signed') or 'pending'}\n"
        f"reviewed: {reviewed}\n"
        f"run: {args.run or carried.get('run', '')}\n"
        f"attempt: {attempt}\n"
        f"mode: {mode}\n"
        f"started: {started}\n"
        f"finished: {finished}\n"
        f"credential_ref: {args.credential_ref or carried.get('credential_ref', '')}\n"
    )
    # `delivers` and `onboarding_pr` sit outside the canonical block (REF-Delivery.md
    # section 1), so each is written only by a line that has one; an empty line would
    # add a field to every record whose line is unphased or whose phase opens no
    # platform pull request.
    if delivers:
        front += f"delivers: {delivers}\n"
    if slug:
        front += f"slug: {slug}\n"
    if surface:
        front += f"surface: {surface}\n"
    if onboarding_pr:
        front += f"onboarding_pr: {onboarding_pr}\n"
    if attests:
        front += f"attests: {attests}\n"
    if claims_attested:
        front += f"claims_attested: {claims_attested}\n"
    if claims_total:
        front += f"claims_total: {claims_total}\n"
    # Run-scoped fields a phase added beyond the canonical block survive the rebuild:
    # dropping what this helper does not know would silently erase recorded evidence.
    # `signed_at` and `outcome` are known and deliberately not written: they are the
    # stamp's closure fields (stamp_gate.py writes them beside `signed:`), and this
    # helper runs only on an open gate (a dated `signed:` refuses above), so a pair it
    # meets describes a closure that is gone. Carried, a re-opened gate would read to
    # the analytics as closed with an outcome, since they read the field before the
    # signature.
    known = {
        "phase", "skill", "status", "gate", "signed", "reviewed", "run",
        "attempt", "mode", "started", "finished", "credential_ref", "delivers", "surface", "slug",
        "onboarding_pr", "attests", "signed_at", "outcome", "claims_attested", "claims_total",
    }
    for key, value in carried.items():
        if key not in known:
            front += f"{key}: {value}\n"
    front += "---\n"
    scratch.mkdir(parents=True, exist_ok=True)
    record.write_text(front + (body if body.startswith("\n") or not body else "\n" + body), encoding="utf-8")

    print(f"Record frontmatter written: {_SCRATCH}/{args.record} (status: {status}, signed: pending).")
    if status == "gate":
        print("Gate reached. Next: the fresh-eyes review, then the signer's stamp (stamp_gate.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
