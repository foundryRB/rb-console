---
title: Glossary
id: DOC-FC-GLOSSARY
type: Reference
status: Active
updated: "2026-10-09"
summary: The console's words, one line each.
---

The words the console's pages and screens use, one line each.

## Terms

| Term | Means |
| --- | --- |
| agent (saved) | a provider endpoint, its credential and the models it serves, saved in Settings and applied to a line or to the home co-pilot |
| archive volume | the console's persistent volume, holding operation receipts and terminal run logs |
| catalog agent | the playbook agent a step runs as: Architect, Designer, Planner, Builder, Librarian, Reviewer, Programmer or Release Manager |
| ceremony | a maintenance act's mode: gated, one-shot or direct |
| close | ending a line: tagging its scratch tip `delivered/<slug>/P<n>`, deleting the ref and ending its runs |
| co-pilot | the toolless advisory agent beside a delivery or the fleet; it advises and never acts |
| command | a request that changes something, keyed by an operation key |
| degraded | a line whose phase record did not finish, parked for a person |
| delivery line | one delivery of an app, scope to learn, recorded on its scratch ref |
| delivery slug | a repository's last path segment, the key a delivery threads through every studio |
| door | an endpoint for one kind of caller: browser, agent, internal or execution |
| drive | launching a line's next phases on the executor |
| establish | creating or adopting a line's repository and registering its scratch ref |
| execution door | the in-cluster door through which the one configured machine caller drives deliveries |
| fresh-eyes review | a phase's own adversarial review, every round committed under `.delivery/reviews/` |
| freshness | an observation's state: loading, fresh, stale or unavailable |
| gate | the signature that closes a phase: proposal, design, plan or delivery |
| gate stamper | the playbook's `stamp_gate.py`, the only writer of `signed:` |
| interactive | the mode in which every gate suspends the run for a person to sign |
| lifecycle pin | the lifecycle definition and playbook revision a line carries in its configuration |
| line card | the cockpit region showing a line's phases, gates and runs |
| one-shot | the mode in which each gate closes over the phase's passing review, with no suspend |
| operation id | the `Idempotency-Key` value that names one act, reused unchanged on a retry |
| operation key | a receipt's key: a digest of the act's scope and its operation id, carried by an unknown outcome |
| operation receipt | the durable record of a command's claim, dispatch and outcome |
| phase | one step of the line: scope, design, intent and plan, build and ship, or learn |
| process truth | what the executor observed of a run: its exit code and its deadline |
| record | a phase's `.delivery/` file, whose canonical frontmatter the resolver reads |
| re-drive | driving a phase again, optionally with feedback threaded into the worker's prompt |
| scratch ref | a line's orphan `delivery/<line>` branch, mounted at `.delivery/` in a working checkout |
| seed | how a line began: new, follow-on, recast or demo |
| studio | a tool a phase drives: estimatekit, protopane or platform-studio; playbook-studio serves the agent catalog |
| verdict | a review's last line: `VERDICT: PASS`, `VERDICT: FAIL` or `VERDICT: UNRECORDED` |
| work truth | what objective validators say of a phase's output: the record exists, its gate is signed |
| worker | the pod that runs one phase's skill, as its catalog agent, judged from outside |

## Read next

- [The console at a glance](../)
- [Decisions](../decisions/)
