"""Stamp a delivery gate: the deterministic step that writes a phase's gate signature.

THE CONTRACT. This file is the single gate stamper for every runner: a person at a
terminal, a console-less one-shot sequencer, and a delivery console's worker and
cockpit all run THIS file (REF-Delivery.md section 1, "How a gate closes"). Treat its
CLI and refusal semantics as a stable interface: runners fetch it pinned and execute
it; they never re-implement it (REF-Delivery.md anti-pattern 30 - a hand-ported stamp
drifts from these guards).

A gate closes in one transaction, whoever drives (REF-Delivery.md section 1): the
record reaches the gate as `status: gate` / `signed: pending` (reach_gate.py, this
folder), the phase's fresh-eyes review passes and is recorded in the frontmatter
`reviewed:` field, and this helper writes the signature. It is the only writer of
`signed:`, in any mode. An agent may run it carrying the signer's relayed approval;
an agent never decides a gate and never offers to sign a pending one.

Evidence it refuses without:
  - one configured phase for the record, with a supported artifact handler in the
    effective `--definition` (default: the canonical lifecycle beside this helper);
  - a passing fresh-eyes review: handed to it as `--review-verdict pass` (recorded
    into `reviewed:`), or already recorded there as a date by a prior
    `--review-only` run;
  - the committed review artifact: `--review-verdict` requires `--review-log`, the
    repo-relative file holding the review's verbatim output (conventionally
    `.delivery/reviews/<record-stem>-<date>-r<N>.md`), whose LAST `VERDICT` token must
    be PASS - the claim and its evidence are read from the same file, so they
    cannot disagree;
  - an open signature: `signed:` present and exactly `pending`; a closed gate is
    never re-stamped.

`--review-only` records a passing review without signing: it writes `reviewed:` and
stops, leaving `signed: pending` for the signer. That is the interactive rhythm: the
review lands first, the signer approves over it, the stamp follows.

The stamp rewrites the frontmatter `signed:` line itself (never a loose `pending`
match elsewhere in the record), writes `reviewed:` if absent, promotes
`status: gate` to `status: complete` (a signed gate is a finished phase; reconcile
requires `complete`), fills an empty `finished:`, and puts a provenance line at the
TOP of the body - directly under the frontmatter, once - so a reader who does not
parse frontmatter reaches the closure BEFORE the phase narration it supersedes
(REF-Delivery.md anti-pattern 24: the stamp creates that contradiction, so the stamp
reconciles it; no earlier review can).

Beside `signed:` (a date, the signer's) it writes two more closure fields in the same
act, both read by the delivery analytics: `signed_at:`, the signing moment as an
ISO-8601 UTC timestamp with seconds, and `outcome:`, how the gate closed, exactly one
of `as it stood`, `with edits`, `re-driven`. The signer states the outcome with
`--outcome`; without the flag it is derived from the record and its committed review
rounds: `re-driven` when the record's `attempt` is greater than 1 or a round of this
record before the passing one ends VERDICT: FAIL, `as it stood` when the first round
passed on a first (or uncounted) attempt. `with edits` is never derived: only a signer
can say a gate closed over edits. A value outside the vocabulary is refused before the
record is touched, and `--review-only` writes neither field.

It also refuses when the scratch carries no `.delivery/journal.md`: the journal is a
phase-exit obligation (REF-Delivery.md section 1), and every phase closes its gate
through this helper, so this is the one place the obligation binds all of them.

Stdlib only. Usage:

    # record the passing review, leave the gate for its signer (interactive)
    python stamp_gate.py --repo <repo-root> --record handoff.md \
        --date 2026-07-16 --review-verdict pass \
        --review-log .delivery/reviews/handoff-2026-07-16-r1.md --review-only

    # stamp the gate: the signer approved (interactive), or the engine closes it
    # over the recorded review (one-shot)
    python stamp_gate.py --repo <repo-root> --record handoff.md \
        --date 2026-07-16 --by "the operator" [--outcome "with edits"] \
        [--review-verdict pass --review-log .delivery/reviews/handoff-2026-07-16-r1.md]
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCRATCH = ".delivery"

# The tolerant verdict read: the LAST `VERDICT` token decides, whatever markdown
# or trailing prose wraps it (the same rule every runner greps by).
_VERDICT_TOKEN = re.compile(r"VERDICT\W*(PASS|FAIL)", re.IGNORECASE)

# The closed outcome vocabulary, spelled as the delivery analytics render it: how a
# gate closed, the signer's word or derived from the record (never `with edits`).
_OUTCOMES = ("as it stood", "with edits", "re-driven")
# The signing moment, UTC to the second: the shape `signed_at:` and `finished:` carry.
_MOMENT = "%Y-%m-%dT%H:%M:%SZ"


def _review_log_refusal(repo: Path, rel: str | None) -> str | None:
    """The refusal line for a review artifact, or None when the artifact holds a
    passing review. The artifact is the review's verbatim output, committed with
    the scratch; its last VERDICT token is the verdict, so the caller's claim and
    the on-disk evidence are one read. The design close (design-session/close_gate.py)
    runs this helper over the record it writes, so this is the one read for every
    phase."""
    if not rel:
        return (
            "REFUSED: --review-verdict carries no evidence without --review-log, the "
            "repo-relative file holding the review's verbatim output (conventionally "
            f"{_SCRATCH}/reviews/<record-stem>-<date>-r<N>.md). Save the review, commit it, "
            "and pass its path."
        )
    if Path(rel).is_absolute():
        return f"REFUSED: --review-log must be repo-relative, got {rel!r}."
    log_path = repo / rel
    if not log_path.is_file():
        return f"REFUSED: review log {rel!r} not found under {repo}."
    text = log_path.read_text(encoding="utf-8")
    if not text.strip():
        return f"REFUSED: review log {rel!r} is empty; not a review."
    tokens = _VERDICT_TOKEN.findall(text)
    if not tokens:
        return f"REFUSED: review log {rel!r} carries no VERDICT token; not a review."
    if tokens[-1].upper() != "PASS":
        return (
            f"REFUSED: review log {rel!r} ends VERDICT: {tokens[-1].upper()}; a failing "
            "fresh-eyes review is a failed attempt, retried fresh - not a signature."
        )
    return None


def _journal_refusal(repo: Path) -> str | None:
    """The refusal line when the scratch carries no journal, or None.

    The journal is a phase-exit obligation, not a habit (REF-Delivery.md section 1).
    Sentiment and the gate-rejection feedback appended before a re-drive have no other
    home and, unlike the evidence chain, are not reconstructable from git - so a line
    that never opened one loses them silently, and reconcile discovers the loss far too
    late to undo it (two real lines reached reconcile with no journal at all). Every
    phase runs this helper to close its gate (anti-pattern 30), which makes the stamp
    the one place the obligation can be enforced for all of them at once.
    """
    if (repo / _SCRATCH / "journal.md").is_file():
        return None
    return (
        f"REFUSED: no {_SCRATCH}/journal.md. Every phase logs its lessons, defects, and "
        "user sentiment as they happen, closed once at reconcile (REF-Delivery.md "
        "section 1, section 6); a phase that logged nothing still leaves the file "
        'present, because "nothing to report" and "nobody reported" are different '
        "states and only the first is trustworthy. Write this phase's entry (an "
        'explicit "no lessons this phase" counts), commit it with the record, and '
        "re-run."
    )


def _front_end(lines: list[str]) -> int | None:
    """Index of the closing `---` of a leading frontmatter block, or None."""
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return None


def _field(lines: list[str], end: int, name: str) -> tuple[int, str] | None:
    """(line index, stripped value) of a frontmatter field, or None when absent."""
    pat = re.compile(rf"^\s*{name}\s*:\s*(.*?)\s*$", re.IGNORECASE)
    for i in range(1, end):
        m = pat.match(lines[i])
        if m:
            return i, m.group(1).strip().strip('"').strip("'")
    return None


def _note_after_front(lines: list[str], note: str) -> None:
    """Put a provenance note at the TOP of the body, under the frontmatter, once.

    Top, not appended. The body is phase narration written *before* the signature, so a
    record whose prose correctly read "the gate awaits its signer" at review time is
    falsified by the very step that closes the gate. No fresh-eyes review can catch a
    contradiction a later step creates, so the stamp owns the reconciliation
    (anti-pattern 24) - and a note buried under the stale narration does not reconcile
    anything: the reader has to reach the authoritative state *before* the prose it
    supersedes, not after.

    Idempotent: repeated `--review-only` runs would otherwise stack byte-identical
    notes, which a real record carried twice.
    """
    stripped = note.strip()
    if any(line.strip() == stripped for line in lines):
        return
    end = _front_end(lines)
    lines.insert(end + 1 if end is not None else 0, f"\n{note}\n")


def _set_field(lines: list[str], end: int, name: str, value: str, after: int) -> None:
    """Write `name: value` into the frontmatter: over the field's own line when the block
    already carries one, else as a new line directly after index `after`. Never twice:
    a duplicate key is two answers to a machine-read question."""
    found = _field(lines, end, name)
    if found is not None:
        lines[found[0]] = f"{name}: {value}\n"
    else:
        lines.insert(after + 1, f"{name}: {value}\n")


def _normalize_outcome(raw: str) -> str | None:
    """The canonical outcome word for a signer's spelling, or None outside the vocabulary.

    Case, hyphens and underscores are tolerated at the door (`re-driven`, `as-it-stood`,
    `WITH_EDITS`) and never in the record: the field is machine-read, and the analytics
    render exactly the three words in _OUTCOMES.
    """
    wanted = " ".join(raw.strip().lower().replace("_", " ").replace("-", " ").split())
    for word in _OUTCOMES:
        if word.replace("-", " ") == wanted:
            return word
    return None


def _review_rounds(repo: Path, record: str) -> list[tuple[tuple[str, int, str], str, Path]]:
    """This record's committed review rounds, oldest first: ((date, round, name), verdict, path).

    A round is `.delivery/reviews/<record-stem>-<date>[-r<N>].md` (REF-Delivery.md
    section 1); one named without a suffix is the single round its record wrote, numbered
    1. A file carrying no VERDICT token is not a review and is left out, and so is one
    that does not read as UTF-8 (a shell redirection can leave a UTF-16 artifact beside
    the others): the derivation informs the outcome, and a sibling file it cannot read
    must not refuse a valid signature. The verdict is the file's LAST token, the same
    read the stamp's own evidence check makes.
    """
    stem = re.escape(Path(record).stem)
    named = re.compile(rf"^{stem}-(\d{{4}}-\d{{2}}-\d{{2}})(?:-r(\d+))?\.md$")
    reviews = repo / _SCRATCH / "reviews"
    rounds: list[tuple[tuple[str, int, str], str, Path]] = []
    if not reviews.is_dir():
        return rounds
    for path in reviews.iterdir():
        match = named.match(path.name)
        if match is None or not path.is_file():
            continue
        try:
            tokens = _VERDICT_TOKEN.findall(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        if not tokens:
            continue
        key = (match.group(1), int(match.group(2) or 1), path.name)
        rounds.append((key, tokens[-1].upper(), path))
    rounds.sort(key=lambda item: item[0])
    return rounds


def _derive_outcome(
    repo: Path, record: str, lines: list[str], end: int, review_log: str | None
) -> str:
    """How the gate closed, read from the record and its committed rounds.

    `re-driven` when the record's `attempt` is greater than 1 (the phase was asked for
    again) or a round of this record before the passing one ends FAIL (a failed review is
    a failed attempt, retried fresh); otherwise `as it stood`: the first round passed on
    a first attempt. An absent `attempt:`, or one this helper cannot read, counts as a
    first attempt: the record helper numbers from 1, and a record it never counted was
    never re-driven. The passing round is the `--review-log` handed in when it is one of
    the record's rounds, else the newest round ending PASS; rounds after it are evidence
    about something other than this closure. `with edits` is never derived: no round and
    no count can say a signer accepted the record over edits, so only `--outcome` does.
    """
    attempt = _field(lines, end, "attempt")
    try:
        count = int(attempt[1]) if attempt is not None and attempt[1] else 1
    except ValueError:
        count = 1
    if count > 1:
        return "re-driven"
    rounds = _review_rounds(repo, record)
    passing = len(rounds)
    if review_log:
        handed = (repo / review_log).resolve()
        passing = next(
            (i for i, (_, _, path) in enumerate(rounds) if path.resolve() == handed), passing
        )
    if passing == len(rounds):
        passed = [i for i, (_, verdict, _) in enumerate(rounds) if verdict == "PASS"]
        passing = passed[-1] if passed else passing
    if any(verdict == "FAIL" for _, verdict, _ in rounds[:passing]):
        return "re-driven"
    return "as it stood"


# --- The gate export (Phases and Artifacts, Foundry principle 02) -------------
#
# Signing a gate is the artifact-creation moment: the stamp's own deterministic
# machinery exports the phase's engineering deliverables into the scratch BEFORE
# the signature lands, whichever door invoked it (a human's button, a system's
# command, an agent's skill step). After the stamp, frozen means frozen: the
# tool's project is legacy and nothing downstream reads it again.
#
#   proposal.md -> estimatekit: the delivered phase's architecture files and the
#                  assumptions, into .delivery/architecture/ and .delivery/assumptions/;
#                  the estimate's effort: the phase's build activities and project
#                  activities verbatim into .delivery/estimate/ (P<n>-build.tsv,
#                  P<n>-project.tsv), and a per-stream effort table appended to the
#                  record itself when it carries none (a point per stream, in MD)
#   design.md   -> protopane: the approved screens' HTML/CSS and the theme, into
#                  .delivery/design/screens/ and .delivery/design/theme.css
#
# A gate with no registered tool (handoff.md, build.md) exports nothing. An
# unreachable tool REFUSES the stamp, as does a missing prototype pointer on the
# design record - a gate cannot freeze what it cannot read. The proposal needs no
# pointer: its project is the repo name (one repo, one estimation project, named
# for it). The export is idempotent: re-running an open gate's stamp overwrites
# the same files, and a record already carrying an effort table keeps the one it has.

# A per-stream table the record already carries: any table whose header row starts
# `| Stream |`, whatever its second column reads (`Effort`, `Effort (MD)`, ...), since
# the consumer reads every `| <stream> | <N> MD |` row it finds and a second table
# beside a hand-written one would hand it duplicate rows. Such a record is left as it
# stands.
_EFFORT_TABLE_HEAD = re.compile(r"^\|\s*Stream\s*\|", re.IGNORECASE | re.MULTILINE)


def _md(value: float) -> str:
    """A person-day figure as the analytics parse it: `125`, `12.5`, never `125.0`."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _effort_by_stream(project_tsv: str, name: str) -> list[tuple[str, float]] | str:
    """(stream, summed MD) in first-seen order from a `P<n>-project.tsv`, or a refusal line.

    The model's per-stream effort (REF-Estimation.md section 3): every project-level
    activity carries a `Stream` and an `Effort (MD)`, the build activities' sum riding
    inside it as the `Build Activities` group, while the resource plan is capacity
    staffed against this effort rather than effort itself. The header row is the file's
    contract, so a file without the two columns refuses, as does a figure that does not
    read as MD (a blank cell included) and a stream name a table row cannot hold (one
    carrying `|`): a gate cannot freeze a number it cannot read, nor a name its readers
    would split. The TSVs carry no quoting convention, so a `"` is a character like any
    other; read as a quote it would open a field that swallows every row below it.
    """
    reader = csv.DictReader(
        io.StringIO(project_tsv.lstrip("﻿"), newline=""),
        delimiter="\t",
        quoting=csv.QUOTE_NONE,
    )
    rows = list(reader)
    columns = {(field or "").strip(): field for field in (reader.fieldnames or [])}
    if "Stream" not in columns or "Effort (MD)" not in columns:
        return (
            f"REFUSED: {name} carries no `Stream` / `Effort (MD)` header (the row is the file's "
            "contract, which the estimatekit door's guide states); the stamp cannot sum effort "
            "per stream from it."
        )
    totals: dict[str, float] = {}
    for row in rows:
        stream = (row.get(columns["Stream"]) or "").strip()
        raw = (row.get(columns["Effort (MD)"]) or "").strip()
        if not stream:
            continue
        if "|" in stream:
            return (
                f"REFUSED: stream {stream!r} in {name} carries a `|`, which a row of the effort "
                "table cannot hold; rename the stream in the estimation project and re-stamp."
            )
        try:
            effort = float(raw)
        except ValueError:
            return (
                f"REFUSED: `Effort (MD)` {raw!r} for stream {stream!r} in {name} is not a "
                "person-day figure (a blank cell is not one either); a gate cannot freeze a "
                "number it cannot read."
            )
        totals[stream] = totals.get(stream, 0.0) + effort
    if not totals:
        return f"REFUSED: {name} carries no stream rows; there is no effort to freeze."
    return list(totals.items())


def _effort_table(phase: str, streams: list[tuple[str, float]]) -> list[str]:
    """The per-stream effort table, in exactly the shape the delivery analytics parse: a
    heading, `| Stream | Effort |`, the separator, one `| <stream> | <N> MD |` row per
    stream, and a final `| Total | <N> MD |` row. A point per stream: the estimate is the
    person-alone baseline (the operator's decision of 2026-09-22), so no range."""
    total = sum(effort for _, effort in streams)
    return [
        f"## Estimated effort ({phase})\n",
        "\n",
        "| Stream | Effort |\n",
        "| --- | --- |\n",
        *(f"| {stream} | {_md(effort)} MD |\n" for stream, effort in streams),
        f"| Total | {_md(total)} MD |\n",
    ]


def _http_get(url: str, user: str, password: str) -> bytes:
    request = urllib.request.Request(url)
    if user:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        return response.read()


def _http_json(url: str, user: str, password: str) -> dict:
    return json.loads(_http_get(url, user, password).decode("utf-8"))


def _export_estimation(repo: Path, text: str, lines: list[str], end: int, args) -> str | None:
    """Export the delivered phase's architecture, assumptions and effort, or a refusal line.

    The effort is frozen twice over, from the phase's activity files: `P<n>-build.tsv`
    and `P<n>-project.tsv` verbatim under `.delivery/estimate/`, and a per-stream table
    (summed from the project activities, REF-Estimation.md section 3) appended to the
    record's body in `lines`, which the stamp writes in the same act as the signature.
    A record already carrying a `| Stream | Effort |` table keeps it.
    """
    delivers = _field(lines, end, "delivers")
    phase = (delivers[1] if delivers else "").strip()
    if not re.fullmatch(r"P\d+", phase, re.IGNORECASE):
        return (
            "REFUSED: proposal.md carries no `delivers: P<n>` frontmatter field; the gate "
            "export cannot pick the phase's architecture without it. Record the pin "
            "through the record helper - `reach_gate.py --delivers P<n>` (this folder) - "
            "never by hand (anti-pattern 30)."
        )
    files_dir = getattr(args, "tool_files_dir", None)
    # The delivery key IS the repo name: one repo, one estimation project, named for it
    # (REF-Delivery section 1, "Phased delivery"), and the DELIVERY-SIDE studios key on
    # that same value (the console's `delivery_slug()`). Only those: platform-studio keys
    # on the app's fleet name, a separate fact, and this helper never addresses it - it
    # stamps the estimation gate. This used to scrape the record's
    # `## Estimation project` section for the first backticked value, which contradicted
    # section 2 - that section is the SIGNER's, carrying full clickable URLs and never
    # slugs - so the first record to follow the doctrine had its instance URL read as a
    # project name, and a live gate refused with a 404.
    slug = args.tool_slug or repo.resolve().name
    if files_dir:
        # The MCP-door path (an OIDC-walled instance's /api is a browser door a
        # plain request cannot pass): the AGENT fetches the project files over
        # the estimation MCP into a local dir mirroring the project tree, and
        # this helper stays the only selector and writer.
        root = Path(files_dir)
        if not root.is_dir():
            return f"REFUSED: --tool-files-dir {files_dir!r} is not a directory."
        listing = {
            "files": [
                {"name": p.name, "path": p.relative_to(root).as_posix()}
                for p in sorted(root.rglob("*"))
                if p.is_file()
            ]
        }

        def _read(src: str) -> str:
            return (root / src).read_text(encoding="utf-8")

        origin = f"--tool-files-dir {files_dir}"
    else:
        base = (args.tool_url or os.environ.get("ESTIMATEKIT_BASE_URL", "")).rstrip("/")
        if not base:
            return (
                "REFUSED: no estimation instance to export from - pass --tool-url (or "
                "ESTIMATEKIT_BASE_URL), or fetch the project files over the estimation "
                "MCP and pass --tool-files-dir (Phases and Artifacts: the proposal stamp "
                "freezes the phase architecture, assumptions and effort into the scratch)."
            )
        user = os.environ.get("ESTIMATEKIT_AUTH_USER", "")
        password = os.environ.get("ESTIMATEKIT_AUTH_PASSWORD", "")
        try:
            listing = _http_json(f"{base}/api/projects/{slug}/files", user, password)
        except (urllib.error.URLError, OSError, ValueError) as err:
            return (
                f"REFUSED: estimation project {slug!r} unreachable at {base} ({err}); a gate "
                "cannot freeze what it cannot read. Bring the instance up (or fix the slug), "
                "or fetch over the MCP door and pass --tool-files-dir, and re-stamp."
            )

        def _read(src: str) -> str:
            payload = _http_json(f"{base}/api/projects/{slug}/files/{src}", user, password)
            return str(payload.get("content", ""))

        origin = base
    phase_lower = phase.lower()
    arch: list[str] = []
    assumptions: list[str] = []
    build_src: str | None = None
    project_src: str | None = None
    for item in listing.get("files", []):
        name = str(item.get("name", "")).lower()
        path = str(item.get("path", ""))
        # Real instances name per-phase files `P2-overview.puml` under
        # `data/architecture/`; the phase token lives in the NAME, the domain in
        # the PATH (matching the name alone misses every real file).
        if "architecture" in path.lower() and (
            name.startswith(f"{phase_lower}-") or f"-{phase_lower}-" in name
        ):
            arch.append(path)
        elif "assumption" in name and (phase_lower in name or not re.search(r"p\d+", name)):
            assumptions.append(path)
        # The phase's effort: `data/activities/P<n>-build.tsv` (the activities) and
        # `data/activities/P<n>-project.tsv` (the per-stream plan the table sums).
        elif "activities" in path.lower() and name == f"{phase_lower}-build.tsv":
            build_src = path
        elif "activities" in path.lower() and name == f"{phase_lower}-project.tsv":
            project_src = path
    if not arch:
        return (
            f"REFUSED: estimation project {slug!r} holds no {phase} architecture files "
            "(the audit mandates them); wrong slug, wrong instance, or an unaudited project."
        )
    if build_src is None or project_src is None:
        return (
            f"REFUSED: estimation project {slug!r} holds no {phase} activities ({phase}-build.tsv "
            f"and {phase}-project.tsv, the per-phase files the estimatekit door's guide states); "
            "the proposal stamp freezes the estimate's effort, and a gate cannot freeze what it "
            "cannot read."
        )
    # Every read and every check comes before the first write, so a refusal leaves
    # nothing behind: a scratch holding half an export beside an unsigned gate would
    # read as frozen to anyone who did not see the refusal.
    contents: list[tuple[str, str, str]] = []
    project_tsv = ""
    for src_paths, dest_dir in (
        (arch, "architecture"),
        (assumptions, "assumptions"),
        ([build_src, project_src], "estimate"),
    ):
        for src in src_paths:
            try:
                content = _read(src)
            except (urllib.error.URLError, OSError, ValueError) as err:
                return f"REFUSED: could not read {src!r} from estimation project {slug!r} ({err})."
            contents.append((dest_dir, Path(src).name, content))
            if src == project_src:
                project_tsv = content
    streams = _effort_by_stream(project_tsv, Path(project_src).name)
    if isinstance(streams, str):
        return streams
    exported: list[str] = []
    for dest_dir, name, content in contents:
        dest = repo / _SCRATCH / dest_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
        exported.append(f"{_SCRATCH}/{dest_dir}/{name}")
    if _EFFORT_TABLE_HEAD.search(text):
        exported.append(f"{_SCRATCH}/{args.record} (effort table already present, kept)")
    else:
        # Appended to the body in `lines`, so the stamp's one write carries the table
        # with the signature; the record's trailing blank lines give way to exactly one.
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        table = _effort_table(phase.upper(), streams)
        lines.append("\n")
        lines.extend(table)
        exported.append(f"{_SCRATCH}/{args.record} (effort table, total {table[-1].strip()})")
    print(f"Gate export ({phase} from estimation project {slug!r} via {origin}): " + ", ".join(exported))
    return None


def _export_prototype(repo: Path, text: str, lines: list[str], end: int, args) -> str | None:
    """Export the approved screens and theme from the prototype, or a refusal line.

    The design close (design-session/close_gate.py) runs this helper, so this is the one
    export for the design gate in both modes.
    """
    if re.search(r"^Prototype:\s*none", text, re.MULTILINE | re.IGNORECASE):
        # No prototype: a tool-less design (REF-Delivery section 3: 3D scenes, non-DOM
        # surfaces captured as prose) or a headless line (section 1, `surface: none`)
        # pins its dimensions as prose in the record itself - the prose IS the
        # deliverable, already in the scratch; nothing external to freeze.
        print("Gate export (design): tool-less design (Prototype: none), a non-DOM surface captured as prose or a headless line; the record's prose is the deliverable.")
        return None
    export_file = getattr(args, "tool_export", None)
    if export_file:
        # The MCP-door path: the AGENT fetches export_project over the
        # prototype MCP and hands the DTO as a file; this helper stays the
        # only writer into the scratch.
        try:
            export = json.loads(Path(export_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            return f"REFUSED: --tool-export {export_file!r} is not readable JSON ({err})."
        slug = args.tool_slug or Path(export_file).stem
    else:
        base = (args.tool_url or os.environ.get("PROTOPANE_BASE_URL", "")).rstrip("/")
        slug = args.tool_slug or ""
        if not base or not slug:
            pointer = re.search(r"Prototype[^:\n]*:\s*(https?://\S+?)/p/([\w-]+)", text)
            if pointer:
                base = base or pointer.group(1)
                slug = slug or pointer.group(2)
        if not base or not slug:
            return (
                "REFUSED: design.md carries no `Prototype: .../p/<slug>` pointer and no "
                "--tool-url/--tool-slug were given; the design stamp freezes the approved "
                "screens, so it must know the prototype (Phases and Artifacts, principle 02)."
            )
        user = os.environ.get("PROTOPANE_AUTH_USER", "")
        password = os.environ.get("PROTOPANE_AUTH_PASSWORD", "")
        try:
            export = _http_json(f"{base}/api/projects/{slug}/export", user, password)
        except (urllib.error.URLError, OSError, ValueError) as err:
            return (
                f"REFUSED: prototype {slug!r} unreachable at {base} ({err}); a gate cannot "
                "freeze what it cannot read. Bring the instance up (or fix the pointer), or "
                "fetch export_project over the prototype MCP and pass --tool-export, and re-stamp."
            )
    design_dir = repo / _SCRATCH / "design"
    screens_dir = design_dir / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "theme.css").write_text(
        str(export.get("theme_css", "")), encoding="utf-8", newline="\n"
    )
    exported = [f"{_SCRATCH}/design/theme.css"]
    for screen in export.get("screens", []):
        screen_slug = str(screen.get("slug", "screen"))
        (screens_dir / f"{screen_slug}.html").write_text(
            str(screen.get("html", "")), encoding="utf-8", newline="\n"
        )
        exported.append(f"{_SCRATCH}/design/screens/{screen_slug}.html")
        css = str(screen.get("css", "") or "")
        if css.strip():
            (screens_dir / f"{screen_slug}.css").write_text(css, encoding="utf-8", newline="\n")
            exported.append(f"{_SCRATCH}/design/screens/{screen_slug}.css")
    # The design-system prompt, when the hub recorded provenance (REF-Design §3:
    # a locked identity is theme PLUS guidance). Absent on hand-authored themes.
    system = export.get("design_system") or None
    if isinstance(system, dict) and str(system.get("guidance", "")).strip():
        (design_dir / "design-system.md").write_text(
            f"# Design system: {system.get('name', system.get('slug', ''))}\n\n"
            f"{str(system.get('guidance', '')).strip()}\n",
            encoding="utf-8",
            newline="\n",
        )
        exported.append(f"{_SCRATCH}/design/design-system.md")
    print(f"Gate export (prototype {slug!r}): " + ", ".join(exported))
    return None


_EXPORTERS = {"proposal": _export_estimation, "design": _export_prototype}
_SUPPORTED_ARTIFACTS = frozenset(json.loads(
    Path(__file__).with_name("artifact-handlers.json").read_text(encoding="utf-8")
))


def _artifact_kind(definition: Path, record: str) -> str | None:
    """Select the record's supported artifact from its effective phase definition."""
    payload = json.loads(definition.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported lifecycle definition")
    phases = payload.get("phases")
    if not isinstance(phases, list) or any(not isinstance(phase, dict) for phase in phases):
        raise ValueError("lifecycle phases must be objects")
    matches = [phase for phase in phases if phase.get("record") == record]
    if len(matches) != 1:
        raise ValueError("the record must belong to exactly one configured phase")
    if "artifact" not in matches[0]:
        raise ValueError("the phase artifact field is required")
    artifact = matches[0]["artifact"]
    if not isinstance(artifact, str) and artifact is not None or artifact not in _SUPPORTED_ARTIFACTS:
        raise ValueError("unsupported phase artifact handler")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Delivery repo root (holds .delivery/)")
    parser.add_argument(
        "--record", required=True, help="Scratch record filename: proposal.md / design.md / handoff.md / build.md"
    )
    parser.add_argument(
        "--definition", type=Path, default=Path(__file__).with_name("lifecycle.json"),
        help="The effective lifecycle definition containing this record's artifact identity. "
        "Defaults to the canonical definition beside the helper.",
    )
    parser.add_argument("--date", required=True, help="Gate (or review) date, YYYY-MM-DD")
    parser.add_argument(
        "--review-verdict",
        help="The fresh-eyes review's verdict for this record. Only 'pass' counts; anything "
        "else refuses - a failing review is a failed attempt retried fresh, never a signature. "
        "Omittable on the stamp only when `reviewed:` already carries the recorded date.",
    )
    parser.add_argument(
        "--by",
        default="the deterministic engine (one-shot)",
        help="Who authorized the signature, for the trail. Interactive stamps MUST name the "
        "approving human (the customer, the operator); the default is only honest in one-shot.",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="Record the passing review in `reviewed:` and stop, leaving `signed: pending` "
        "for the signer (the interactive rhythm; requires --review-verdict pass).",
    )
    parser.add_argument(
        "--tool-url",
        help="The phase tool's base URL for the gate export (proposal: estimatekit; design: "
        "protopane). Defaults: ESTIMATEKIT_BASE_URL / PROTOPANE_BASE_URL env, or the "
        "record's own pointer (design.md's Prototype line).",
    )
    parser.add_argument(
        "--tool-slug",
        help="The phase tool's project slug for the gate export. Defaults to the repo "
        "folder name for the proposal (one repo, one estimation project, named for it), "
        "and to the design record's `Prototype: .../p/<slug>` pointer for the design.",
    )
    parser.add_argument(
        "--tool-files-dir",
        help="Proposal export, MCP-door path: a local directory mirroring the estimation "
        "project's file tree, fetched by the agent over the estimation MCP when the "
        "instance's /api sits behind a browser login. The helper stays the only "
        "selector and writer.",
    )
    parser.add_argument(
        "--tool-export",
        help="Design export, MCP-door path: a JSON file holding the prototype's "
        "export_project DTO, fetched by the agent over the prototype MCP when the "
        "instance's /api sits behind a browser login.",
    )
    parser.add_argument(
        "--review-log",
        help="Repo-relative path of the committed review artifact: the fresh-eyes review's "
        "verbatim output (conventionally .delivery/reviews/<record-stem>-<date>-r<N>.md). "
        "Required with --review-verdict; the helper reads the file's LAST VERDICT token, "
        "so the claimed verdict and the on-disk evidence cannot disagree.",
    )
    parser.add_argument(
        "--outcome",
        help="How the gate closed, for the trail and the delivery analytics: exactly one of "
        "'as it stood', 'with edits', 're-driven' (case, hyphens and underscores are "
        "tolerated at the door). Omitted, the helper derives it from the record's "
        "`attempt` and its committed review rounds; `with edits` is never derived, only a "
        "signer can say it. Refused with --review-only: the outcome is the stamp's.",
    )
    args = parser.parse_args()

    try:
        artifact = _artifact_kind(args.definition, args.record)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"REFUSED: cannot select this record's artifact handler: {exc}")
        return 1

    if not _DATE.match(args.date):
        print(f"FAIL: --date must be YYYY-MM-DD, got {args.date!r}")
        return 1
    outcome = None
    if args.outcome is not None:
        outcome = _normalize_outcome(args.outcome)
        if outcome is None:
            print(
                f"REFUSED: --outcome {args.outcome!r} is outside the vocabulary; the field is "
                "machine-read, so it carries exactly one of 'as it stood', 'with edits', "
                "'re-driven'. Nothing is recorded."
            )
            return 1
        if args.review_only:
            print(
                "REFUSED: --review-only records a review, not a closure, so it cannot carry "
                "--outcome; the outcome is the signer's word at the stamp. Pass it there."
            )
            return 1
    verdict = args.review_verdict.strip().lower() if args.review_verdict else None
    if verdict is not None and verdict not in ("pass", "passed"):
        print(
            f"REFUSED: review verdict is {args.review_verdict!r}, not a pass; nothing is "
            "recorded (a failing fresh-eyes review is a failed attempt, retried fresh - not a signature)."
        )
        return 1
    if verdict is not None:
        refusal = _review_log_refusal(Path(args.repo), args.review_log)
        if refusal:
            print(refusal)
            return 1

    record = Path(args.repo) / _SCRATCH / args.record
    if not record.is_file():
        print(f"FAIL: no {_SCRATCH}/{args.record} at {args.repo}")
        return 1
    journal_refusal = _journal_refusal(Path(args.repo))
    if journal_refusal:
        print(journal_refusal)
        return 1
    lines = record.read_text(encoding="utf-8").splitlines(keepends=True)

    end = _front_end(lines)
    if end is None:
        print(
            f"FAIL: {args.record} has no frontmatter block; nothing to stamp. "
            "Run reach_gate.py first (REF-Delivery.md section 1)."
        )
        return 1
    signed = _field(lines, end, "signed")
    if signed is None:
        print(f"FAIL: {args.record} frontmatter has no `signed:` field (run reach_gate.py first).")
        return 1
    si, sval = signed
    if _DATE.match(sval):
        print(f"REFUSED: {args.record} gate is already signed ({sval}); a closed gate is never re-stamped.")
        return 1
    if sval.lower() != "pending":
        print(f"FAIL: {args.record} `signed:` is {sval!r}, expected `pending`.")
        return 1
    reviewed = _field(lines, end, "reviewed")
    gate = _field(lines, end, "gate")
    gate_name = gate[1] if gate and gate[1] else Path(args.record).stem

    if args.review_only:
        if verdict is None:
            print("REFUSED: --review-only records a review, so it requires --review-verdict pass.")
            return 1
        if reviewed is not None:
            lines[reviewed[0]] = f"reviewed: {args.date}\n"
        else:
            lines.insert(si + 1, f"reviewed: {args.date}\n")
        _note_after_front(
            lines,
            f"> Fresh-eyes review passed {args.date} (VERDICT: PASS; artifact `{args.review_log}`); "
            f"recorded in `reviewed:`. The {gate_name} gate awaits its signer "
            "(REF-Delivery.md section 1). Prose below predates the review.",
        )
        record.write_text("".join(lines), encoding="utf-8")
        print(f"Review recorded in {_SCRATCH}/{args.record}: reviewed: {args.date}; signed stays pending.")
        print("Hand the gate to its signer; the stamp follows their approval.")
        return 0

    reviewed_recorded = reviewed is not None and bool(_DATE.match(reviewed[1] or ""))
    if verdict is None and not reviewed_recorded:
        print(
            "REFUSED: no review evidence. Pass --review-verdict pass, or record the review "
            "first with --review-only; a gate does not close without its fresh-eyes review "
            "(REF-Delivery.md section 1)."
        )
        return 1

    # The gate export precedes the signature (Phases and Artifacts, principle 02):
    # the stamp freezes the phase tool's deliverables into the scratch, or refuses.
    exporter = _EXPORTERS.get(artifact)
    if exporter is not None:
        refusal = exporter(Path(args.repo), "".join(lines), lines, end, args)
        if refusal:
            print(refusal)
            return 1

    # The stamp: the frontmatter `signed:` line itself becomes the date; `reviewed:` is
    # recorded if it was not already; `status: gate` becomes `status: complete` (a signed
    # gate is a finished phase); an empty `finished:` is filled. Every runner that stamps
    # a gate runs this same block, so the trail reads the same everywhere.
    #
    # Beside the signature, in the same act, the closure's two machine-read fields:
    # `signed_at:` (the moment, so idle time resolves to the second rather than the day)
    # and `outcome:` (how the gate closed: the signer's word, else derived from the
    # record). Each is written over a line the block already carries rather than added
    # beside it: a record that reaches this stamp carrying one describes a closure that
    # is gone, and two answers to a machine-read question is no answer.
    now = datetime.now(timezone.utc).strftime(_MOMENT)
    if outcome is None:
        outcome = _derive_outcome(Path(args.repo), args.record, lines, end, args.review_log)
    lines[si] = f"signed: {args.date}\n"
    if reviewed is not None:
        if not reviewed_recorded:
            lines[reviewed[0]] = f"reviewed: {args.date}\n"
    else:
        lines.insert(si + 1, f"reviewed: {args.date}\n")
    end = _front_end(lines) or end
    _set_field(lines, end, "signed_at", now, after=si)
    end = _front_end(lines) or end
    _set_field(lines, end, "outcome", outcome, after=_field(lines, end, "signed_at")[0])
    end = _front_end(lines) or end
    status = _field(lines, end, "status")
    if status is not None and status[1].lower() == "gate":
        lines[status[0]] = "status: complete\n"
    elif status is not None and status[1].lower() not in ("complete",):
        print(
            f"NOTE: status is {status[1]!r}, expected `gate` at a stamp (reach_gate.py sets it); left as-is."
        )
    finished = _field(lines, end, "finished")
    if finished is not None and not finished[1]:
        lines[finished[0]] = f"finished: {now}\n"
    artifact = f"; artifact `{args.review_log}`" if verdict is not None else ""
    _note_after_front(
        lines,
        f"> Gate closed: {gate_name} signed {args.date} by {args.by} over a passing "
        f"fresh-eyes review (REF-Delivery.md section 1{artifact}). Prose below predates "
        "the closure; the frontmatter is the gate.",
    )
    record.write_text("".join(lines), encoding="utf-8")

    print(
        f"Gate stamped in {_SCRATCH}/{args.record}: signed: {args.date} (by {args.by}), "
        f"signed_at: {now}, outcome: {outcome}, status: complete."
    )
    print("Commit and push the record; the run's pre-flight and reconcile read the frontmatter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
