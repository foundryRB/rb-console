---
title: "0010 · Lines follow the installed worker"
id: DOC-FC-ADR-0010
type: Reference
status: Active
updated: "2026-10-07"
adr_status: Decided
summary: "A line launches on the installed, versioned worker image when the installation executes its pinned playbook revision; a line with no pin adopts the installed definition on its next drive."
---

A line launches on the installed, versioned worker image when the installation executes its pinned
playbook revision; a line with no pin adopts the installed definition on its next drive.

- Status: accepted
- Date: 2026-10-06, extended 2026-10-07
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R167, INT-FC-R172

## Context

Console releases change the worker image while lines are in flight, and lines are opened by hand
from the playbook, by earlier consoles, and by the console itself. A line must run on a worker that
executes its playbook revision, and the console must not keep every historical image runnable.

## Decision

- Each line pins its lifecycle definition and playbook revision. A launch runs on the installed,
  versioned or digest-pinned worker image when the installation executes that revision, and is
  refused with its reason otherwise.
- A line that carries no pin is observed with the installed definition and, on its next drive,
  adopts it: the pin is committed beside the line's configuration before the run is submitted
  (extended 2026-10-07, after a line opened by an earlier console could not be driven at all).

## Alternatives considered

- **Pin each line to the worker image that established it.** Rejected: old images accumulate, and
  an old image cannot run a newer playbook's helpers.
- **Refuse an unpinned line until it is established again.** Rejected: an established line cannot
  be established again, so such a line could never be driven.

## Consequences

- An install upgrade moves every in-flight line to the new worker at its next phase.
- A playbook revision the installed worker cannot execute stops launches until the install catches
  up, and the refusal names that.
