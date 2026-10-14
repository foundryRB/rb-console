---
title: "0006 · The console runs its own executor"
id: DOC-FC-ADR-0006
type: Reference
status: Active
updated: "2026-10-08"
adr_status: Decided
summary: "Delivery phases run as an Argo Workflow on the console's own single-namespace executor; the console compiles and reads back, and writes no execution engine."
---

Delivery phases run as an Argo Workflow on the console's own single-namespace executor; the console
compiles and reads back, and writes no execution engine.

- Status: accepted
- Recorded: 2026-10-08, from the console's design as built
- Deciders: operator (rafaelgpires)

## Context

A phase is a long, unattended agent run that can crash, hang or exceed its budget. Something has to
hold its live state in-cluster, retry it within a bound, kill it at a deadline and park it at a gate
until a person signs. Writing that machinery inside the console would make the console a scheduler,
and the console stays optional and thin by its principles' prime directive.

## Decision

The console compiles a line's remaining phases into an Argo Workflow and submits it to its own
single-namespace Argo Workflows executor. A phase is one step; bounded retries are the step's
`retryStrategy`; a timeout is its `activeDeadlineSeconds`; an interactive gate is a `suspend` step.
The executor owns retries, deadlines, suspend and resume, and the live run state; the console reads
back the executor's observation as process truth. Ship stays delegated to Argo CD, the reconciler
that already exists for it.

## Alternatives considered

- **A process the console spawns and supervises.** Rejected: the console would own retries,
  deadlines and crash recovery, and a console restart would lose every live run.
- **A shared, cluster-wide executor.** Rejected: one namespace keeps the console's service account
  scoped to its own workflows.

## Consequences

- A console restart loses no run; the Workflow object is the live state.
- The worker is an activity judged from outside: its exit code and its deadline are observed by the
  executor, never reported by the worker.
- Submitted workflows keep their compiled inputs and image through later console releases.
