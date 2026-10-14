---
title: Principles
id: DOC-FOUNDRY-CONSOLE-002
type: Standard
status: Active
updated: "2026-10-08"
summary: The hardened, testable invariants the Console must never soften.
---

Non-negotiable, phrased as **testable rules**. Each has a check you can run against the design. If a
check fails, the design is wrong, not the check.

## 0. Prime directive: optional · non-central · never load-bearing

The Console is never required. Every phase, gate, and tool is fully operable by hand and by the
existing headless path, with no Console.

- **Test A (uniqueness):** name one thing the Console can do that nothing else can. If you can, it has
  become load-bearing; that is the bug.
- **Test B (deletion):** delete the Console. Every delivery still completes and stays trustworthy.
- **Test C (need):** you never *have* to open it to make progress.

## 1. No dependency inversion

The Console depends on the tools; the tools never depend on it, are never adapted to it, never know it
exists.

- **Test:** building or changing the Console requires **zero edits** to any tool, skill, or REF. The
  moment a change to a tool "so the Console can…" is proposed, stop: the dependency just inverted.

## 2. Derived state, never stored truth

Delivery progress is derived from the committed records on each repository's `delivery/*` scratch ref. Git remains authoritative for delivery evidence. Observation caches can be rebuilt from their owners.

Command receipts and archived run evidence have a different lifetime: they preserve dispatch outcomes and terminal execution facts. They live on the persistent archive volume and survive process restarts. An uncertain write requires authoritative resolution before another attempt.

- **Test:** rebuilding observations changes no delivery evidence, while an uncertain command remains blocked after restart.

## 3. Federates only; adds no capability

Anything the Console does, it does by invoking an operation the tools/skills/owners **already** expose
(including "create a repo", which is a GitHub operation). It gathers scattered capability into one
pane; it never introduces a new one.

- **Test:** every Console action maps 1:1 to an existing owner operation, skill, or CLI command a human
  could run instead.

## 4. Drive-through-owners: acts at will, owns nothing

The Console may trigger **any** action, but always **through the owner** (GitHub, git, a tool's door,
a spawned worker), never by writing an owner's artifact directly, and never because it *must*.

- **Test:** every write the Console causes is performed by the owner and is byte-for-byte what a human
  running that command by hand would produce.

## 5. Gates stay the moat

Human sign-off at **proposal · design · plan · delivery** is preserved exactly. The Console surfaces a
gate and routes the signature through the playbook's own gate stamper (`stamp_gate.py`, run over the
record by Sign and by the worker alike); it never stamps a gate itself, never skips one, and the
stamper refuses a gate whose fresh-eyes review was never recorded ([The gate mechanism](../reference/gates/)).

- **Test:** a gate closed via the Console is indistinguishable from one closed by hand.

## 6. Deterministic core; the orchestrator launches agents, it never is one

The control flow is code: same inputs, same next step. The only model in the drive path is the
**worker** the orchestrator *launches* to run a phase or a maintenance act. The Console exposes REST
(for the operator's buttons) and **no `/mcp`**: the would-be consumer of a console MCP door is a
Claude session that already holds the playbook and the owners' own doors - the co-pilots beside the
panes advise and are toolless by design.

- **Test:** removing the co-pilot changes nothing about the control flow; no model ever decides
  the next step; `GET /mcp` is a 404; and a button can *start* a phase because "start" means "code,
  launch the worker," not "button, be the worker."

## 7. The chat advises; feedback still pays the gate

Principle 6 keeps the model out of the control flow. This one governs the conversational surface the
Console *does* have. Its co-pilots are advisory (`INT-FC-R44`), toolless by design and **launched**
toolless rather than asked to be (`INT-FC-R71`): a co-pilot reads the pane's context and *stages* what
the operator might do, most concretely a fenced `redrive` block the composer pre-fills, and never
performs the act itself.

Nor does the Console ever grow a cheaper path around a gate. Operator feedback re-enters a line only as
a committed re-drive, which pays the full cold read of the phase: the worker is a fresh pod with no
memory of the turn being corrected, so it re-reads the repo, the studio, and the committed review trail
before it revises anything. A lane that skipped the audit or the fresh-eyes review to make that cheaper
would be a discount on the guarantee, not a feature. The agentic conversation, the one that *acts*,
stays in the agent's own frontend; the Console does not reimplement it.

- **Test A (stages, never acts):** every co-pilot launch passes `--tools ""`, and no co-pilot turn
  mutates a `.delivery/` record, a gate, or a run.
- **Test B (no side door):** name a path by which operator feedback reaches a worker without first being
  committed to the repo. If one exists, the fast lane has been built.

## Why this doesn't erode the moat

An "everything app" that orchestrates *sounds* like an anti-thesis to a trust model built on gates and
proof. It isn't, **because of the rules above.** The Console holds no trust (2, 5), owns nothing (4),
adds no capability (3), and is never required (0). It is to the Delivery Line what a CI dashboard is to
CI: convenient, never the thing being trusted.

## Read next

- [The delivery module](../modules/delivery/): how these invariants shape a line, its records and
  its gates.
- [The execution module](../modules/execution/): the worker as an activity, judged on two truths.
