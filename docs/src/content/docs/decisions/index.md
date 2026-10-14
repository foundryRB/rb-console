---
title: Decisions
id: DOC-FC-DECISIONS
type: Reference
status: Active
updated: "2026-10-09"
summary: The console's decision log, the one home of the reasons behind its design.
---

The decision log holds the why behind the console's design: each record states its context, the
decision and its consequences, and the alternatives it weighed where it weighed any. The rest of the site describes what
is; read a record here when you need to know why it is that way.

## Current

| Decision | In one line |
| --- | --- |
| [0001 · Per-phase git identities](0001-per-phase-git-identities/) | Every catalog agent and the console role act as their own configured machine-user identity; there is no shared or default git identity. |
| [0002 · Run-log history is self-contained](0002-run-logs-self-contained/) | A terminal run's logs are snapshotted onto the console's own archive volume, so the run history never depends on the observability stack. |
| [0003 · The delivery scratch lives on an orphan branch](0003-delivery-scratch-orphan-branch/) | A delivery line's records live on its own orphan `delivery/<line>` branch, mounted at `.delivery/` in a working checkout and never on the default branch. |
| [0004 · Catalog agents name the workers](0004-catalog-agents-name-the-workers/) | Each phase step runs as the playbook catalog agent its phase names, and identities and labels key on that agent. |
| [0005 · The gate review is the phase's](0005-the-gate-review-is-the-phases/) | The phase runs its own fresh-eyes review; the entrypoint only locates the newest committed review, reads its verdict and stamps over a PASS. |
| [0006 · The console runs its own executor](0006-the-console-runs-its-own-executor/) | Delivery phases run as an Argo Workflow on the console's own single-namespace executor; the console compiles and reads back, and writes no execution engine. |
| [0007 · A protocol per caller](0007-a-protocol-per-caller/) | A studio serves three doors, each for one kind of caller: a browser door behind OIDC, an agent door over MCP, and an in-cluster REST door for the console's own reads and writes. |
| [0008 · One machine caller through an execution door](0008-one-machine-caller-through-an-execution-door/) | The benchmark reaches the console through an in-cluster execution door with its own bearer token, holding only the delivery-execution actions on its own repositories. |
| [0009 · No presence dial](0009-no-presence-dial/) | A delivery has a mode, interactive or one-shot, and no attended or unattended presence setting; a worker that needs a person stops, and the operator re-drives with feedback. |
| [0010 · Lines follow the installed worker](0010-lines-follow-the-installed-worker/) | A line launches on the installed, versioned worker image when the installation executes its pinned playbook revision; a line with no pin adopts the installed definition on its next drive. |
| [0011 · A fifteen-minute freshness window](0011-a-fifteen-minute-freshness-window/) | Repository metadata is fresh for fifteen minutes; the scheduler collects each repository once it is due within that window, a few at a time, and an explicit refresh sweeps them all. |
| [0012 · Teams from identity-provider groups](0012-teams-from-identity-provider-groups/) | Several teams share one install: membership comes from identity-provider groups, the team-to-project mapping and the saved agents' owner levels live in the console's settings, and every read and command is scoped to the caller's teams. |

## Superseded

No decision has been superseded.

## Read next

- [The console at a glance](../)
- [Glossary](../glossary/)
