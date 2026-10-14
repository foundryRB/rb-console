---
title: Worker stops
id: DOC-FOUNDRY-CONSOLE-008
type: Reference
status: Active
updated: "2026-10-09"
summary: The exit codes a worker returns when it stops on purpose - degraded, delivery-scale, wrong-repo, session-limit and stamp-refused - what each one means, what the Console does with it, and the act that clears it; and how a whole run being stopped on purpose differs from one that failed.
---

A worker exits non-zero for two very different reasons, and the number says which. Most non-zero exits are **transient**: something went wrong, a retry may well fix it, and the executor retries the phase up to its budget. A short table of codes in the 60s are **terminal stops**: the worker decided, on purpose, that no retry can help, so the executor does not retry and the run parks for you. This page is what those numbers mean.

The Console names a stop in its own words wherever it reports one. A code that is not in this table keeps the executor's own wording.

## The terminal stops

| Code | Stop | What happened | What clears it |
| --- | --- | --- | --- |
| 64 | `degraded` | The phase's record is stamped `status: aborted`. The agent hit a deterministic blocker it must not work around - a missing authorization, an unsigned gate, a contract it cannot satisfy. | Read the record's own reason, remove the blocker, re-drive the phase. |
| 65 | `delivery-scale` | A resolve worker judged the ticket too big for a maintenance scope: a rework, a new subsystem, work spanning several PRs. No PR was opened. The prepared delivery brief is already a comment on the ticket and the ticket carries the `foundry-delivery-scale` label. | Press **Switch to Delivery** on the ticket, which pre-fills the delivery form from that comment (from the ticket's body when no comment carries the marker). Or re-drive with a prompt that forces a maintenance-sized change. |
| 66 | `wrong-repo` | A resolve worker found the ticket's fix lives in a different repo, so this repo can hold no branch, no conformance run and no PR for it. The owning repo is named in a comment on the ticket, which carries the `foundry-wrong-repo` label. | Transfer the ticket to the owning repo and drive it from that repo's loop. The Console never transfers a ticket for you. |
| 67 | `session-limit` | The agent hit the model's own quota wall - a session or usage window, or a limit on the one model this phase runs. Terminal because the wall is a rolling clock window: retrying immediately burns the whole attempt budget against a still-closed door. | Wait for the window to reset, then re-drive. Nothing else is wrong with the run. If the wall named a single model, re-driving the phase on another model clears it without the wait. |
| 68 | `stamp-refused` | A one-shot gate's stamp refused over the phase's passing fresh-eyes review: the studio was down, an export was refused, or the record is one the stamper will not close. The review is recorded with `signed: pending`, the stamper's refusal line is written on the record as `stamp_refused:`, and the record is pushed, so the line reads awaiting that gate with the refusal in its next command. Terminal because a retry re-runs the whole phase into the same closure. | Sign the gate from the cockpit, which exports through the record's link, then drive the line on in one-shot. When Sign refuses with the same line, the record caused it: re-drive the phase, with feedback when it helps. |

Every other non-zero exit is transient and retried. A code like 137 or 143 is the container being killed rather than the worker choosing to stop - most often a Stop or Terminate you pressed, or the run passing its deadline.

## A stopped run is not a failed run

The stops above are the *worker's* - one phase deciding it cannot continue. A whole **run** can also be closed deliberately, and that is a different thing again. It happens two ways: you press **Stop** or **Terminate** on the run controls, or the Console stops a run for you when you drive the same delivery again: one delivery has one live run.

Argo has five workflow phases - Pending, Running, Succeeded, Failed, Error - and no phase for a deliberate close, so a shutdown lands in `Failed`. The Console does not report that: it records **who** stopped the run on the run itself, in the same act that requests the shutdown, and reads the phase back from its own mark.

| Phase | What it means |
| --- | --- |
| `Stopping` | A shutdown was asked for and the run is draining. A graceful Stop lets the current step finish its exit handler, and a worker's step can run to its whole deadline, so this is a state you will genuinely see - not a blink. |
| `Stopped` | The run is over, closed on purpose. Amber in the band, never red. Hover the phase to read which act ended it. |

A run that had already reached its own outcome keeps it: a run that was `Succeeded` when a re-drive superseded it still reads `Succeeded`, and one that had genuinely failed still reads `Failed`. So a red row in the band is a real failure, every time.

**`Stopped` is not `superseded`.** The band writes `· superseded` on every row that is not the newest, which answers *where a run sits in the history* - a question independent of how it ended. A run stopped by the Console is usually both; a run that failed on its own two weeks ago and was overtaken later is superseded without ever having been stopped.

## Where you see one

A stop's name rides the run-completed event, and the Maintenance pane and the one-shot judge's ledger report it, so the pane reads `parked: delivery-scale stop` rather than only that a run failed; a delivery run's row carries who stopped it. The raw line the executor recorded - `main: Error (exit code 65)` - stays visible in the node inspector for the step that returned it, alongside that step's logs. Every step also leaves its own last refusal line as its `refusal` output on the Workflow object, and the cockpit shows a failed delivery run's line beside its `Failed` pill, so the reason survives the pod.

## Where the codes are defined

The table lives once, in `orchestrator/domain/services/run_policy.py`. The Console compiles Argo's retry expression from it, so the codes it declines to retry are exactly the ones above; the worker script it builds re-declares them for the shell; the Maintenance pane reads the two ticket labels; and this page carries their prose. A test holds all four in agreement, so a stop cannot be added in one place and mean nothing in another.
