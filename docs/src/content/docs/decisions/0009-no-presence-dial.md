---
title: "0009 · No presence dial"
id: DOC-FC-ADR-0009
type: Reference
status: Active
updated: "2026-10-08"
adr_status: Decided
summary: "A delivery has a mode, interactive or one-shot, and no attended or unattended presence setting; a worker that needs a person stops, and the operator re-drives with feedback."
---

A delivery has a mode, interactive or one-shot, and no attended or unattended presence setting; a
worker that needs a person stops, and the operator re-drives with feedback.

- Status: accepted
- Recorded: 2026-10-08, from the console's design as built
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R39

## Context

An early design carried a presence dial, attended or unattended, beside the run mode. It was
persisted, labelled and displayed, and consumed by nothing. The executor runs ephemeral pods with
headless agents: no worker can pause for a person mid-run, and an answer given later would land in
a fresh pod anyway.

## Decision

There is no presence dial. Mode is the one delivery-level setting. A worker that genuinely needs a
person fails its attempt and the line parks degraded; the operator answers by re-driving the phase
with feedback, which threads into the next worker's prompt.

## Alternatives considered

- **Keep the dial and make a worker wait for an answer.** Rejected: a worker is a headless pod with
  no channel to a person, and holding a pod for an answer spends its deadline doing nothing.
- **An attended mode that pauses at the next step boundary.** Rejected: the gate suspend of
  interactive mode already pauses between phases, and re-drive with feedback answers inside one.

## Consequences

- The configuration read serves no presence field, the compiled workflow carries no presence
  environment or label, and a stale presence key is scrubbed on the next save.
- Re-drive with feedback covers the whole attended use case.
