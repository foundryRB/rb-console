---
title: "0007 · A protocol per caller"
id: DOC-FC-ADR-0007
type: Reference
status: Active
updated: "2026-10-08"
adr_status: Decided
summary: "A studio serves three doors, each for one kind of caller: a browser door behind OIDC, an agent door over MCP, and an in-cluster REST door for the console's own reads and writes."
---

A studio serves three doors, each for one kind of caller: a browser door behind OIDC, an agent door
over MCP, and an in-cluster REST door for the console's own reads and writes.

- Status: accepted
- Recorded: 2026-10-08, from the console's design as built
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R115

## Context

Three different callers reach a studio: a person in a browser, the worker agents, and the
console's backend. Each needs a different protocol and a different credential. Mixing them either
drags browser sign-in into server calls or abuses tool invocation as RPC.

## Decision

| Door | Caller | Protocol and auth | Why this protocol |
| --- | --- | --- | --- |
| Human: the public host's SPA and `/api` | a person in a browser | REST behind OIDC (Keycloak) | the browser flow needs cookies and sign-in |
| Agent: `/mcp` on the public host | worker agents, and the console's tool-shaped reads | MCP with per-door Basic auth | tool discovery and invocation is what MCP is for |
| Internal: `/api` on the in-cluster `internal` Service port | the console's backend | REST, in-cluster only | deterministic reads and writes are RPC, not tool calls; MCP is not app-to-app glue |

The internal door targets the studio's app container past its OIDC sidecar, on a Service port the
Gateway never routes, so the port names the east-west trust boundary rather than hiding it. The
console's deterministic reads of a studio's substance and every platform-studio call, writes
included, ride it, so the agent credential never signs the cockpit's acts. What is tool-shaped
stays a tool call: the console's health probes, the studios' project inventories and the playbook's
agent catalog are MCP calls. A transport failure on the internal door is a source failure, and the
console tries no second door: a refused write retried through another door is one write become
two.

## Alternatives considered

- **One door for every caller.** Rejected: the browser door's OIDC sign-in cannot serve a pod, and
  an agent door shared with the console would let the agent credential sign the cockpit's acts.
- **MCP for the console's reads and writes.** Rejected: deterministic reads and writes are RPC,
  and a tool call answers prose where the console needs typed data and typed refusals.
- **Falling back to the MCP door when the internal port is unreachable.** Rejected: a refused write
  retried through a second door is one write become two.

## Consequences

- The cockpit renders a studio's substance natively instead of framing an OIDC-gated authoring UI.
- A refusal on the internal door is typed data (a status and the exception class), not a string to
  parse.
- A refused MCP write is an error in its own right, never an empty result.
- A studio whose internal port is unreachable reads as unavailable until it answers.
