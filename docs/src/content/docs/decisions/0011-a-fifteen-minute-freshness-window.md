---
title: "0011 · A fifteen-minute freshness window"
id: DOC-FC-ADR-0011
type: Reference
status: Active
updated: "2026-10-06"
adr_status: Decided
summary: "Repository metadata is fresh for fifteen minutes; the scheduler collects each repository once it is due within that window, a few at a time, and an explicit refresh sweeps them all."
---

Repository metadata is fresh for fifteen minutes; the scheduler collects each repository once it is
due within that window, a few at a time, and an explicit refresh sweeps them all.

- Status: accepted
- Date: 2026-10-06
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R107, INT-FC-R169

## Context

The fleet board reads per-repository metadata from GitHub: maintenance and promotion state,
promotion options, and delivery configuration. Reading every repository on every two-minute tick
spends the request budget on data that has not changed; reading too rarely leaves the board stale.
A tick also has other observations to make, so collection has to fit beside them.

## Decision

- An observation is fresh for fifteen minutes.
- Each tick collects, oldest first and in a bounded batch, the repositories whose last attempt is
  older than the window less two ticks, a few repositories at a time, publishing each as it lands.
- The operator's explicit refresh reads every repository at once.

## Alternatives considered

- **Collect every repository on every tick.** Rejected: the request volume grows with the fleet for
  data that rarely changes.
- **A window measured from each tick's observed duration.** Rejected: the measurement fed back into
  the due rule and let a slow tick widen its own window.

## Consequences

- A healthy fleet stays fully fresh without reading any repository before it is due.
- A failed read keeps the last good data and reads as stale or unavailable, never as fresh.
