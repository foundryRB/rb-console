"""Write a worker run's figures into its phase record: the deterministic writer of the
``run`` and ``run_*`` frontmatter keys (foundry-console#115), so no agent and no shell
edit hand-writes a record for them.

The worker runs ``claude -p ... --output-format stream-json`` and keeps the raw stream.
Its final ``result`` event carries what the run cost: ``total_cost_usd``, ``num_turns``,
``usage`` (input, output, cache-creation and cache-read tokens) and, on recent harnesses,
``modelUsage`` (the same per model). This helper reads that event off the stream and
records it beside the record helper's block as flat keys, the keys foundry-analytics
reads for a phase's ledger:

    run                 the run id the console knows this run by
    run_agent           the catalog agent that ran the phase
    run_model           the model it ran with: --model, else the busiest model the event reports
    run_started         ISO-8601 UTC, when the agent was launched
    run_finished        ISO-8601 UTC, when the result event arrived
    run_seconds         the agent's own run time, launch to result event, in whole seconds
    run_tokens          every token type summed, across every model the event reports usage
                        for (so the work the agent delegated counts), else off its top-level
                        usage, which covers the agent's own turns alone
    run_cost            USD, six decimals
    run_tokens_input, run_tokens_output, run_tokens_cache_read, run_tokens_cache_creation
    run_turns
    run_permission_denials
                        how many calls the harness refused this run (its result event's
                        permission_denials), added across attempts like the other counts
    run_model_<slug>_tokens, run_model_<slug>_cost
                        per model the event reports; the slug is the model id lower-cased
                        with every non-alphanumeric character as ``_``

A second run against the same record (an executor retry of the attempt, or a re-drive)
ADDS tokens, cost, turns and seconds, keeps the earliest ``run_started`` and the latest
``run_finished``, and names the latest run, agent and model. The span is the record's
first start and last finish, which can hold a night between two attempts; ``run_seconds``
is the accumulated agent execution time. When the record has no run_seconds key, its
recorded start-to-finish span initializes the sum. A backwards clock leaves this
attempt's duration unrecorded. Every other byte of the record is preserved: a
key already present is rewritten on its own line, a new one is appended at the end of the
block in the file's own line endings, and nothing outside these keys is read or written.

Figures are telemetry, never a reason a phase fails. A record that does not exist, a
record with no frontmatter block, a stream that cannot be read and a stream with no
result event each write nothing, say so on one line, and exit 0. Only the helper's own
arguments are refused.

Stdlib only. Usage:

    python record_run.py --repo <repo-root> --record build.md --stream agent.jsonl \\
        --run delivery-app-x7k2p --agent builder --model claude-opus-4-1 \\
        --started 2026-09-22T10:00:00Z --finished 2026-09-22T10:12:34Z
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["figures_from_event", "main", "merge_figures", "read_result_event"]

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_SCRATCH = ".delivery"
#: A frontmatter line this helper owns: `run`, or any `run_*` key, at column 0 - the flat
#: block's own shape. Nothing else is read or rewritten, so `running:`, an indented `run:`
#: under a nested key, or a `run_tokens: 999` in the body is never touched.
_OWNED = re.compile(r"^(run(?:_[A-Za-z0-9_]+)?)\s*:\s*(.*?)\s*$")
#: The order a first write appends the keys in; per-model keys follow, sorted by slug.
_ORDER = (
    "run",
    "run_agent",
    "run_model",
    "run_started",
    "run_finished",
    "run_seconds",
    "run_tokens",
    "run_cost",
    "run_tokens_input",
    "run_tokens_output",
    "run_tokens_cache_read",
    "run_tokens_cache_creation",
    "run_turns",
    "run_permission_denials",
)
_IDENTITY = ("run", "run_agent", "run_model")
_TOKEN_TYPES = (
    ("run_tokens_input", ("input_tokens", "inputTokens")),
    ("run_tokens_output", ("output_tokens", "outputTokens")),
    ("run_tokens_cache_read", ("cache_read_input_tokens", "cacheReadInputTokens")),
    ("run_tokens_cache_creation", ("cache_creation_input_tokens", "cacheCreationInputTokens")),
)


def _stamp(value: str) -> datetime | None:
    """An ISO stamp as an aware datetime (a zoneless one read as UTC), or None."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _front_end(lines: list[str]) -> int | None:
    """Index of the closing `---` of a leading frontmatter block, or None."""
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return None


def _owned_fields(lines: list[str], end: int) -> dict[str, str]:
    """The `run` / `run_*` values the block already carries, quotes stripped."""
    fields: dict[str, str] = {}
    for i in range(1, end):
        m = _OWNED.match(lines[i].rstrip("\r\n"))
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fields


def _first(mapping: dict[str, object], *names: str) -> object:
    """The value under the first of `names` present in `mapping`, or None."""
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _int(value: object) -> int:
    """A count read tolerantly: anything that is not a number counts as nothing."""
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float | None:
    """A figure read tolerantly, or None when the value carries no number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _money(value: float) -> str:
    """USD to six decimals: a run that cost 0.00003 reads as its cost, never as free."""
    return f"{value:.6f}"


def _slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", model.lower())


def read_result_event(stream: Path) -> dict[str, object] | None:
    """The last `result` event on the stream, or None when it carries none or cannot be read.

    One JSON object per line is the stream-json contract; a line that is not JSON, or not
    an object, is skipped rather than raised on - a stderr line that leaked in, a truncated
    tail - because the stream is evidence of what the run cost, and one stray line's shape
    is not evidence that it cost nothing.
    """
    try:
        text = stream.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    event: dict[str, object] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            event = obj
    return event


def figures_from_event(event: dict[str, object], model: str = "") -> dict[str, object]:
    """The keys this run contributes, as typed values, from the result event alone.

    Only what the event carries is contributed: a harness that reports no cost writes no
    `run_cost`, rather than a zero that reads as "free". `run_model` is the `model` handed
    in (the model the worker was launched with), else the model the event reports the most
    tokens for, else nothing.
    """
    figures: dict[str, object] = {}
    usage = event.get("usage")
    if isinstance(usage, dict):
        by_type = {key: _int(_first(usage, *names)) for key, names in _TOKEN_TYPES}
        figures.update(by_type)
        figures["run_tokens"] = sum(by_type.values())
    cost = _float(_first(event, "total_cost_usd", "totalCostUsd"))
    if cost is not None:
        figures["run_cost"] = cost
    turns = _first(event, "num_turns", "numTurns")
    if turns is not None:
        figures["run_turns"] = _int(turns)
    denials = _first(event, "permission_denials", "permissionDenials")
    if isinstance(denials, list):
        # What the harness refused this run: a nonzero count beside a failed phase points at
        # a permission mode or a policy, not the agent's work (INT-FC-R193).
        figures["run_permission_denials"] = len(denials)
    busiest, busiest_tokens = "", -1
    per_model = _first(event, "modelUsage", "model_usage")
    across = {key: 0 for key, _ in _TOKEN_TYPES}
    reported = False
    if isinstance(per_model, dict):
        for model_id, entry in per_model.items():
            name = str(model_id).strip()
            if not name or not isinstance(entry, dict):
                continue
            for key, names in _TOKEN_TYPES:
                across[key] += _int(_first(entry, *names))
            reported = True
            tokens = sum(_int(_first(entry, *names)) for _, names in _TOKEN_TYPES)
            figures[f"run_model_{_slug(name)}_tokens"] = tokens
            model_cost = _float(_first(entry, "costUSD", "cost_usd", "costUsd"))
            if model_cost is not None:
                figures[f"run_model_{_slug(name)}_cost"] = model_cost
            if tokens > busiest_tokens:
                busiest, busiest_tokens = name, tokens
    if reported:
        # The top-level usage counts the agent's own turns; the per-model usage also counts
        # the subagents it delegated to, and is what total_cost_usd was charged for.
        figures.update(across)
        figures["run_tokens"] = sum(across.values())
    chosen = model.strip() or busiest
    if chosen:
        figures["run_model"] = chosen
    return figures


def _earliest(prior: str, stamp: str) -> str:
    before, now = _stamp(prior), _stamp(stamp)
    return prior if before is not None and now is not None and before < now else stamp


def _latest(prior: str, stamp: str) -> str:
    before, now = _stamp(prior), _stamp(stamp)
    return prior if before is not None and now is not None and before > now else stamp


def merge_figures(existing: dict[str, str], new: dict[str, object]) -> tuple[dict[str, str], list[str]]:
    """The rendered values to write, and the notes worth printing.

    Counts and costs add to what the record already carries (a retried attempt still cost
    what it cost), the span keeps its earliest start and latest finish, and the identity
    keys name the latest run. A carried figure that is not a number is noted and replaced:
    a malformed value is not evidence of a prior spend.
    """
    merged: dict[str, str] = {}
    notes: list[str] = []
    for key, value in new.items():
        prior = existing.get(key, "")
        if key in _IDENTITY:
            if str(value):
                merged[key] = str(value)
        elif key == "run_started":
            merged[key] = _earliest(prior, str(value))
        elif key == "run_finished":
            merged[key] = _latest(prior, str(value))
        elif key == "run_seconds" and not prior:
            # Initialize a missing run_seconds value from the recorded span.
            start, end = _stamp(existing.get("run_started", "")), _stamp(existing.get("run_finished", ""))
            carried = int((end - start).total_seconds()) if start and end and end >= start else 0
            merged[key] = str(carried + _int(value))
        elif key.endswith("_cost"):
            carried = _float(prior)
            if prior and carried is None:
                notes.append(f"NOTE: `{key}: {prior}` is not a figure; replaced by this run's.")
            merged[key] = _money((carried or 0.0) + float(value))  # type: ignore[arg-type]
        else:
            if prior and not prior.lstrip("-").isdigit():
                notes.append(f"NOTE: `{key}: {prior}` is not a count; replaced by this run's.")
            merged[key] = str(_int(prior) + _int(value))
    return merged, notes


def _rewrite(lines: list[str], end: int, merged: dict[str, str]) -> tuple[int, int]:
    """Rewrite the owned lines in place and append the missing keys before the closing
    fence, in the file's own line endings. Returns (keys added, keys rewritten)."""
    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    pending = dict(merged)
    rewritten = 0
    for i in range(1, end):
        m = _OWNED.match(lines[i].rstrip("\r\n"))
        if not m or m.group(1) not in pending:
            continue
        ending = lines[i][len(lines[i].rstrip("\r\n")):]
        lines[i] = f"{m.group(1)}: {pending.pop(m.group(1))}{ending}"
        rewritten += 1
    ordered = [k for k in _ORDER if k in pending] + sorted(k for k in pending if k not in _ORDER)
    lines[end:end] = [f"{key}: {pending[key]}{newline}" for key in ordered]
    return len(ordered), rewritten


def main() -> int:
    if "--record-status" in sys.argv[1:]:
        parser = argparse.ArgumentParser(description="Read canonical phase record status")
        parser.add_argument("--record-status", required=True, type=Path)
        args = parser.parse_args()
        # The worker image copies the same domain reader used by observation sources.
        # Repository execution resolves that package from this helper's source tree.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from orchestrator.adapters.outbound.records.yaml_record_parser import parse
        from orchestrator.domain.model.record_status import RecordStatus

        try:
            frontmatter = parse(args.record_status.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            frontmatter = None
        if frontmatter is None or frontmatter.status not in set(RecordStatus):
            print("Record status is unavailable or unsupported", file=sys.stderr)
            return 1
        print(frontmatter.status)
        return 0

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", required=True, help="Delivery repo root (holds .delivery/)")
    parser.add_argument("--record", required=True, help="Scratch record filename: proposal.md / build.md")
    parser.add_argument(
        "--stream", required=True, help="The agent's raw stream-json output, one event per line"
    )
    parser.add_argument("--run", default="", help="The run id the console knows this run by")
    parser.add_argument("--agent", default="", help="The catalog agent that ran the phase")
    parser.add_argument(
        "--model",
        default="",
        help="The model the worker was launched with; absent, the event's busiest model is recorded",
    )
    parser.add_argument("--started", required=True, help="ISO-8601 stamp of the agent's launch")
    parser.add_argument(
        "--finished", default="", help="ISO-8601 stamp of the result event's arrival (default: now, UTC)"
    )
    args = parser.parse_args()

    started = args.started.strip()
    if _stamp(started) is None:
        print(f"REFUSED: --started {args.started!r} is not an ISO 8601 timestamp.")
        return 1
    finished = args.finished.strip() or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if _stamp(finished) is None:
        print(f"REFUSED: --finished {args.finished!r} is not an ISO 8601 timestamp.")
        return 1

    record = Path(args.repo) / _SCRATCH / args.record
    if not record.is_file():
        print(
            f"NOTE: no {_SCRATCH}/{args.record} at {args.repo}; the run ended before its record "
            "exists, so its figures are not recorded."
        )
        return 0
    event = read_result_event(Path(args.stream))
    if event is None:
        print(
            f"NOTE: {args.stream} carries no result event; the run's figures are not recorded "
            f"in {_SCRATCH}/{args.record}."
        )
        return 0
    lines = record.read_bytes().decode("utf-8").splitlines(keepends=True)
    end = _front_end(lines)
    if end is None:
        print(
            f"NOTE: {_SCRATCH}/{args.record} has no frontmatter block; the run's figures are "
            "not recorded (the record helper writes the block)."
        )
        return 0

    new = figures_from_event(event, args.model)
    if args.run.strip():
        new["run"] = args.run.strip()
    if args.agent.strip():
        new["run_agent"] = args.agent.strip()
    new["run_started"] = started
    new["run_finished"] = finished
    # This attempt's own run time. A clock that stepped backwards records none: a zero
    # would read as a real figure.
    ran = int((_stamp(finished) - _stamp(started)).total_seconds())  # type: ignore[operator]
    if ran >= 0:
        new["run_seconds"] = ran
    merged, notes = merge_figures(_owned_fields(lines, end), new)
    for note in notes:
        print(note)
    added, rewritten = _rewrite(lines, end, merged)
    record.write_bytes("".join(lines).encode("utf-8"))
    print(
        f"Run figures recorded in {_SCRATCH}/{args.record}: {merged.get('run_tokens', '?')} tokens, "
        f"{merged.get('run_cost', '?')} USD, {merged.get('run_turns', '?')} turns "
        f"({added} keys added, {rewritten} rewritten)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
