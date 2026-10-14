---
title: "0004 · Catalog agents name the workers"
id: DOC-FC-ADR-0004
type: Reference
status: Active
updated: "2026-08-22"
adr_status: Decided
summary: "Each phase step runs as the playbook catalog agent its phase names, and identities and labels key on that agent."
---

Each phase step runs as the playbook catalog agent its phase names, and identities and labels key on that agent.

- Status: accepted
- Date: 2026-08-22
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R138, R139, R140, R141; revises R90
- Ticket: #62

## Context

Every phase ran a worker pod, and every worker was anonymous: the run log said a phase ran, it
could not say who ran it. ADR-0001 assigned a machine-user git identity per phase, positionally,
so the Settings grid read as seven slots rather than as who holds which account.

The playbook now holds an agent catalog: one definition per distinct worker (REF-Universe
section 4) with a name, a job title, the one-line description a harness routes on, the skills it
is licensed to run, the doors it needs, its posture, and the paragraph it runs under. The catalog
is served over playbook-studio's door, the same door the workers already pull their skills from.

## Decision

The Console binds every step it runs to a named catalog agent, beside the step's skill, and keeps
that binding in its own domain: each delivery phase its phase worker (Estimator, Designer,
Planner, Builder, Librarian), every gate's fresh-eyes review the Reviewer, the maintenance acts
the Programmer (resolve, reconcile-docs) and the Reviewer (review), the promotion door the
Release Manager. The corpus names the people; the Console names who it hands each step to. P1
holds: no tool, skill or REF learns the Console exists.

At launch the service reads the roster once over the studio's MCP door. The compiler stamps the
agent's name on the worker template (FC_AGENT, and the `foundry-console/agent` label) and, when
the catalog answered, its posture and its paragraph beside it. The entrypoint announces the agent
in the pod log, appends the paragraph as the system prompt verbatim, and honours `writes: false`
as the runtime's editing-tool denylist; the permission mode rides as information, since nothing
in a headless pod can stop to ask. The gate review is the Reviewer the same way.

The git identity map is keyed on the agent, not the step. The Settings grid lists the agents
with the steps each runs; the identity assigned to an agent reaches every step that agent runs.

The run row, the node graph, and the pod log say who ran each step, read back off the Workflow
object's own template labels.

A catalog that cannot be read degrades to the named but anonymous worker of before, byte-identical
in every other field, and is recorded at warning in the orchestrator's log. A run is never refused
for want of a roster.

## Consequences

- The stored role -> identity map's keys change from step keys (`scope`, `maintenance-resolve`,
  `promote`) to agent names (`estimator`, `programmer`, `release-manager`). The old keys are
  dropped by the map, never aliased: there is no permanent code for a transient migration. After
  the deploy the operator re-assigns the identities once in Settings; until then every step is
  unassigned and cannot push, which is the same fail-loud posture ADR-0001 chose for an
  unassigned phase.
- The catalog adds one MCP read per drive and no new dependency.
- The desk and the cockpit can now name the same people: the terminal's own cast (foundry-terminal#24)
  becomes the same catalog read over the same door.
