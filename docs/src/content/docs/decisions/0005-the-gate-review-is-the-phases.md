---
title: "0005 · The gate review is the phase's"
id: DOC-FC-ADR-0005
type: Reference
status: Active
updated: "2026-09-06"
adr_status: Decided
summary: "The phase runs its own fresh-eyes review; the entrypoint only locates the newest committed review, reads its verdict and stamps over a PASS."
---

The phase runs its own fresh-eyes review; the entrypoint only locates the newest committed review, reads its verdict and stamps over a PASS.

- Status: accepted
- Date: 2026-09-06
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R150; revises R52, R102, R103, R104, R138, R141, R146
- Companion: the playbook's REF-Delivery section 1 ("The runner spawns no review of its own")
  and anti-patterns AP-40 and AP-41 state the doctrine; this record holds the console-specific
  reasoning and mechanics.

## Context

Every delivery phase runs a fresh-eyes adversarial review of its own output before its record
reaches its gate: the playbook's `adversarial-review` skill, spawned by the phase as a clean agent
pass with no share of the phase's context, its report committed under `.delivery/reviews/`.
The worker entrypoint then ran a second review at the gate: a three-check prompt of its own
wording, handed to the catalog's Reviewer, over the same committed record. That prompt was
written on 2026-07-10; the skill it approximated was born on 2026-07-16, carrying a
`kind=record` lens for exactly this gate close, and the entrypoint was never pointed at it.

Three costs followed, all visible in live lines (moments-app, `delivery/2026-08-25`; Alexandria,
`delivery/2026-08-02`):

- The gate review re-read bytes the phase's own final PASS had just covered, and each fresh
  reviewer's different taste over the same bytes produced new findings that were variance,
  not defects. An operator journaled the loop as "running on diminishing returns".
- On PASS the entrypoint wrote its report to `<record-stem>-<date>.md`, the same name a phase
  review already used, and overwrote it.
- On FAIL it discarded the report and exited; the executor retried the whole phase cold, with
  no record of what had failed.

The console's own rule is that it binds catalog agents and runs the playbook's helpers unported
(ADR-0004, "one stamper, zero hand-ports"). A review prompt in the entrypoint restated the skill
by hand, the same shape as the hand-ported stamp this project already removed once.

## Decision

The gate's evidence is the phase's own review, and the entrypoint's part at a gate is
mechanical:

1. **Locate.** The record's newest review artifact under `.delivery/reviews/`, the files named
   `<record-stem>-*.md`, newest by version order (so `-r10` follows `-r9`; the playbook names
   every round `<record-stem>-<date>-r<N>.md`, FAIL rounds included).
2. **Read.** The artifact's last `VERDICT:` token, with the markdown-tolerant parse of
   INT-FC-R102.
3. **Stamp.** Only over a PASS, through the vendored `stamp_gate.py` with that artifact as
   `--review-log`, exactly as before. Interactive records it (`--review-only`) and suspends
   for the human; one-shot stamps.

A record at its gate with no artifact, or whose newest artifact does not end PASS, exits
non-zero after pushing the scratch as it stands, so the failing round reaches the remote and the
retried phase reads it as its prior (the skill derives it). The entrypoint spawns no reviewer
and carries no review prompt, and the compiler binds no reviewer to a delivery step: the
`FC_REVIEWER` environment is gone. The Reviewer remains the maintenance loop's review agent.

The alternative, keeping one console-spawned review at the gate but running the skill with
`kind=record` over the phase's committed review, was considered and set aside: it keeps a model
in the console's loop for a check whose honest form is a lookup, and its value (an independent
pass the producer cannot forge) is the same class of protection the self-sign fail-safe already
gives the signature. It stays available if forged reviews ever appear.

## Consequences

- One review per round, always the skill's, always with the phase's context excluded; the gate
  costs a file lookup.
- A failing round is evidence, not waste: it is committed, and the retry starts warm.
- The phase's own artifact is never overwritten by the runner.
- Trust at the gate rests on the phase having run the skill. The stamper still refuses a gate
  without a committed artifact ending PASS, and the self-sign fail-safe still strips a
  hand-written signature; a phase that fabricates a PASS artifact is the residual risk, the same
  one the maintenance loop's reconcile audit exists to surface.
