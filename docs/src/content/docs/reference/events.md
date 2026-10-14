---
title: Events
id: DOC-FOUNDRY-CONSOLE-012
type: Reference
status: Active
updated: "2026-10-08"
summary: "The facts the Console states on the platform event bus: one row per type under the delivery and maintenance domains it owns, with the subject and the pointers each carries. The consumer's contract, held equal to the publisher by a test."
---

The Console owns the `delivery` and `maintenance` domains on the platform's event bus by its own grant (the platform's `onboard-events` guide), and states one fact per act it performs and per change its refresh tick observes. This page is the contract a consumer reads, `foundry-routines` first among them: the types, what each is about, and what `data` carries. It is held equal to the publisher's constants by the test suite (`tests/test_events.py`), so a row here is a type the Console emits and nothing else is.

Every event is a CloudEvent with `source` `/foundry/foundry-console` and `datacontenttype` `application/json`. Each carries identity and pointers (the repo, the phase, the run handle, the pull request number), never a record body: a consumer treats an event as a hint and reads the scratch, the repo host, or the executor for the truth, because positions stay derived and never stored (P2). Publishing is one-way (`REF-Events` section 6): a publish that cannot be delivered is dropped and logged, and the act completes unchanged, which `INT-FC-R137` attests for every act below.

## Delivery

| Type | `subject` | Published when | `data` |
| --- | --- | --- | --- |
| `com.foundry.delivery.line.started` | the repo | a delivery line is established or first started (its scratch laid down) | `repo`, `birth` (how the repo came to be, on establish) |
| `com.foundry.delivery.phase.started` | the repo | a phase's worker run is submitted to the executor | `repo`, `phase`, `run_id`, `handle`, `mode`, `revision` |
| `com.foundry.delivery.phase.entered` | the repo | the tick finds a line's derived position moved to a new phase to run | `repo`, `phase`, `previous_status`, `previous_phase` |
| `com.foundry.delivery.gate.reached` | the repo | the tick finds a line parked at an unsigned gate | `repo`, `phase`, `gate`, `previous_status`, `previous_phase` |
| `com.foundry.delivery.gate.signed` | the repo | the operator signs the gate a line is parked on | `repo`, `gate` |
| `com.foundry.delivery.phase.reopened` | the repo | the operator re-opens a signed phase for review | `repo`, `phase` |
| `com.foundry.delivery.run.completed` | the run | the tick finds a run reached a terminal phase (`Succeeded`, `Failed`, `Error`, `Stopped`) | `run`, `handle`, `repo`, `phase`, `stop` (the named stop, when the console defines one), `mode`, `maintenance`, `ticket` |
| `com.foundry.delivery.run.degraded` | the repo | the tick finds a line degraded: a phase record did not finish (aborted, or left in-progress) | `repo`, `phase`, `previous_status`, `previous_phase` |
| `com.foundry.delivery.line.delivered` | the repo | the tick finds every gate signed | `repo`, `previous_status`, `previous_phase` |
| `com.foundry.delivery.line.learned` | the repo | the tick finds the journal stamped learned | `repo`, `learned_on`, `previous_status`, `previous_phase` |
| `com.foundry.delivery.line.closed` | the repo | the operator closes the line (its scratch ref tagged and deleted) | `repo`, `scratch_ref`, `learned_on` |

## Maintenance

| Type | `subject` | Published when | `data` |
| --- | --- | --- | --- |
| `com.foundry.maintenance.act.launched` | the repo | a maintenance act's worker run is submitted (resolve, review, reconcile-docs) | `repo`, `act`, `target` (the ticket or pull request number), `mode`, `run_id`, `handle` |
| `com.foundry.maintenance.pr.judged` | the repo | the one-shot judge reads the verdict recorded on the driven pull request | `repo`, `pr`, `ticket`, `verdict`, `checks`, `gate` (what the judge will do) |
| `com.foundry.maintenance.pr.merged` | the repo | a pull request is merged, by the operator's press or by the judge on a recorded PASS | `repo`, `pr`, `ticket` (judge only), `by` (`operator` or `judge`) |
| `com.foundry.maintenance.act.parked` | the repo | a one-shot act parks for the operator, with the judge's own reason | `repo`, `ticket`, `handle`, `reason` |
| `com.foundry.maintenance.ticket.closed` | the repo | the operator closes a ticket whose merged pull request did not | `repo`, `ticket` |

## What is not stated

The tick primes its view on a cold start and narrates nothing it merely found: a restart never replays the history of every line and run it can see. A read that finds nothing moved states nothing. No read path of the Console consumes its own events; the stream is never the store.

Adding a type is one change to this page and to `orchestrator/application/events.py` together; the test refuses either alone.
