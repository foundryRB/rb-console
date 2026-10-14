---
title: Promotion, proven to target
id: DOC-FC-FLOW-PROMOTION
type: Flow
status: Active
updated: "2026-10-08"
summary: How a proven release moves to a target its app's promotion contract declares, through the promote skill and the target's door.
---

A promotion starts from the app's proven release, its highest semver tag, and a target that does
not carry it yet. It ends with the target carrying the release and its declared signal
read, or with the door in flight on the pair.

## Sequence

```mermaid
sequenceDiagram
  autonumber
  actor Op as Operator
  participant C as Console
  participant GH as GitHub
  participant A as Argo executor
  participant RM as Release Manager worker
  C->>GH: read devops/promotion.yaml, the highest release tag, each target's state
  C-->>Op: one row per target: pending, in flight, unproven, unreadable, up to date
  Op->>C: drive promote(repo, target)
  C->>A: submit the promotion run
  A->>RM: promote
  RM->>GH: open the target's door: deploy-branch values, or a promote/<release> pull request
  RM->>RM: verify terms, then acceptance
  C->>GH: read the target again
  C-->>Op: up to date, or in flight while the door is open
```

## Steps

1. The console reads the app's promotion contract (`devops/promotion.yaml`), its highest semver tag
   as the proven release, and each target's state, and shows one row per target.
2. A row reads pending when the proven release is ahead of what the target carries. The operator
   drives the promotion for that target.
3. The console submits a run in which the Release Manager runs the `promote` skill: its pre-flight
   confirms the entry environment serves the release, then it performs the target's door (an
   environment's values on the install's deploy branch, or a pair's `promote/<release>` pull
   request) and verifies the target's terms and then its acceptance.
4. While a door is open and has not landed the row reads in flight, and a second promotion is not
   the next act. Once the target carries the release and its signal answers, the row reads up to
   date.

## Read next

- [A bench delivery through the execution door](../bench-delivery/)
- [The promotion module](../../modules/promotion/)
