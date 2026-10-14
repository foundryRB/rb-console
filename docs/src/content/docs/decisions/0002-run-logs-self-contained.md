---
title: "0002 · Run-log history is self-contained"
id: DOC-FC-ADR-0002
type: Reference
status: Active
updated: "2026-07-27"
adr_status: Decided
summary: "A terminal run's logs are snapshotted onto the console's own archive volume, so the run history never depends on the observability stack."
---

A terminal run's logs are snapshotted onto the console's own archive volume, so the run history never depends on the observability stack.

- Status: accepted
- Date: 2026-07-27
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R108, R109, R110
- Companion: the platform's ADR-038 (observability is a one-way dependency) states the
  platform-wide rule this decision instantiates; this record holds the console-specific
  reasoning and mechanics.

## Context

The cockpit's run band shows the executor's runs and their worker logs. The logs live in
the worker pods, and every compiled Workflow carries a GC policy (INT-FC-R95) that
deletes those pods a bounded delay after the run completes - so a superseded or failed
run's logs went dark long before the operator was done with them, which is what made
re-driving destroy the previous run's evidence (the pain that motivated the run-history
band).

The platform's observability stack already ingests every pod's logs into Loki, so the
obvious shortcut was to serve historical run logs from Loki. The console would have
gained history for free - at the cost of a runtime dependency on the monitoring
namespace, on Loki's retention, and on LogQL. Verified live before deciding: Loki's
collector was also *missing* most worker `main` output for short-lived pods, so the
shortcut would have shipped a history pane that was quietly emptier than the live view.

## Decision

The console keeps its run-log history itself, and never reads the observability stack.

- A **snapshot store** on the console's own data volume (`FC_RUN_LOG_DIR`, default
  `/data/run-logs`, one file per run keyed by Workflow name) captures each terminal
  run's pod-prefixed log tail exactly once. The **background refresh tick** drives the
  capture off the executor read it already makes, so a run that finishes with no cockpit
  open is still captured well inside the pod-GC delay; a page's own runs read sweeps
  too. An empty capture is saved as the swept marker so a lost run is probed once, never
  per tick. (INT-FC-R108)
- **Log reads fall back to the snapshot** when the live pods are gone, and both sources
  serve node-scoped reads by the same pod-matching rule, so a run's logs read
  identically the hour after pod GC and the week after. (INT-FC-R109)
- **Retention is one operator setting** (Settings page, `run-retention`): the pod GC
  delay and the success/failure Workflow TTLs, read live per compile into every
  Workflow's GC block; the snapshot prune horizon *is* the failure TTL, so a run's row
  in the band and its log file always expire together. (INT-FC-R110)
- **The obs stack is for humans.** Grafana/Loki remain the cross-app, historical,
  queryable surface over everything - including these same worker logs - and the
  console may link there; it never calls Loki, Prometheus, or Grafana APIs on any
  control or serving path (platform ADR-038).

## Alternatives considered

- **Query Loki for historical run logs.** Rejected: a runtime dependency on the
  monitoring namespace for a core cockpit surface (the stack is deliberately allowed to
  be down), lock-in to Loki's query language and label scheme against a stack the
  platform intends to keep swappable, and - measured live - worse data than the
  snapshot, since the collector missed most short-lived worker pods' `main` output.
- **Stretch the pod GC delay instead of snapshotting.** Rejected: pods are the most
  expensive way to store text (etcd objects, kubelet state, node disk held per
  container), the delay would trade cluster hygiene for retention, and any node reclaim
  still loses the logs. The snapshot is a few KB per run on a volume the console
  already mounts.
- **Argo's own log archival (`archiveLogs` to an artifact repository).** The
  Argo-native shape, but it requires deploying and operating an object store (MinIO)
  plus artifact-repository config for a single-namespace executor whose whole log
  volume is megabytes. Disproportionate today; the snapshot store can be swapped for it
  behind the same port if an artifact repo ever arrives for other reasons.

## Consequences

- Run history is bounded by the retention setting (defaults: green runs a week, failed
  runs and every snapshot a month) - operator-tunable per install, no redeploy, applied
  from the next drive. Anything longer-lived is Grafana/Loki's job, on the obs stack's
  own retention, as a human surface rather than a console feature.
- The console works identically with the monitoring namespace absent, degraded, or
  replaced; swapping Loki for anything else touches nothing here.
- The snapshot is a tail (deep enough for a phase's worker output), not a byte-complete
  archive; a pathological run that logs beyond it loses its oldest lines. Accepted: the
  band is an operational surface, not an audit log.
