---
title: "0008 · One machine caller through an execution door"
id: DOC-FC-ADR-0008
type: Reference
status: Active
updated: "2026-10-07"
adr_status: Decided
summary: "The benchmark reaches the console through an in-cluster execution door with its own bearer token, holding only the delivery-execution actions on its own repositories."
---

The benchmark reaches the console through an in-cluster execution door with its own bearer token,
holding only the delivery-execution actions on its own repositories.

- Status: accepted
- Date: 2026-10-07
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R173

## Context

The benchmark opens, configures, drives and closes bench deliveries with nobody in the loop, and
grades them afterwards. Every console door admitted only a person signed in through the browser,
so the benchmark could not establish a line at all. The console serves no `/mcp`, by principle:
driving deliveries is the operator's act, and an outside agent gets no lever.

## Decision

- A second web-tier listener serves the delivery-execution operations alone (establish, the agent
  list, applying an agent to a line, the line's mode and phase timeout, drive, state, run status,
  close), published by its own ClusterIP Service that the Gateway never routes.
- The caller presents a bearer token held in a Secret seated out of band. The backend admits it as
  a machine principal holding only those actions, on repositories the installation names under its
  own owner.
- The model is chosen from the console's saved agents: the caller applies an agent and one of its
  models to the line, and a machine drive names no worker endpoint, provider, model or credential.
  The console's stored credential therefore reaches no endpoint but the agent's.
- A machine establish carries the ask alone; the caller seeds its repository with its own
  credential.

## Alternatives considered

- **Admit identity-provider client-credentials tokens at the sign-in proxy.** Rejected: the proxy
  would admit machine tokens on every route, and the backend would still need a narrower rule.
- **Reuse an operator's session or token.** Rejected: the benchmark would act with an operator's
  whole authority.
- **A committed configuration file naming the model and carrying a copied key.** Rejected: the
  operator chooses among the console's saved agents, and the credential stays in the console.

## Consequences

- One more Secret per install and one more in-cluster address, both absent until the chart enables
  the door; an unseated token leaves the door refusing everything.
- Every machine command names a repository and is recorded under `execution#<name>`.
- A worker still holds its credential while it runs, and the caller's seed is code the worker
  reads, so the door narrows the lever without making a delivery's content trusted.
