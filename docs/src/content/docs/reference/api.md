---
title: API conventions
id: DOC-FC-REF-API
type: Reference
status: Active
updated: "2026-10-08"
summary: The rules every console endpoint follows - where it is served, how a command is keyed and checked, what an error carries, and how a read reports its freshness.
---

Every endpoint is served under `/api` and documented once, in the module that owns it: each module
page's HTTP surface lists its operations, and together they cover the API's OpenAPI export
(`frontend/src/models/openapi.json`) exactly. This page holds the conventions they share.

## Where it is served

| Door | Address | Admits |
| --- | --- | --- |
| The browser door | the install's public host, through the sign-in proxy | an operator the app realm admits |
| The execution door | `http://<release>-execution.<namespace>.svc.cluster.local:8081`, in-cluster only | the one configured machine caller, with its bearer token, for the delivery-execution operations alone |

The backend itself listens on loopback inside the pod; nothing reaches it but the web tier.

## Commands

A command is any `POST` or `DELETE` that changes something. Four `POST`s start background work or
compute a view and are not commands: `/api/fleet/refresh`, `/api/fleet/chat`,
`/api/deliveries/chat` and `/api/deliveries/plan`.

| Header | Required | Meaning |
| --- | --- | --- |
| `Idempotency-Key` | yes, on every command | the operation id: one value per act, reused unchanged when the same act is retried |
| `If-Match` | where the command acts on a source revision | the revision the caller read (a line's `revision` from its state), as one strong value |
| `Authorization: Bearer <token>` | on the execution door only | the machine caller's credential; the browser door strips it |

A line's state carries its `revision`. A command whose `If-Match` no longer matches answers a
conflict; the caller reads the state again before it acts.

## Errors

Every error body is `{code, message, detail}`, with `operation_key` when the outcome is unknown.
The operation key is the receipt's own key, a digest of the act's scope and its operation id.

| Status | `code` | Means | Was anything done? |
| --- | --- | --- | --- |
| 403 | `permission_denied` | no current grant permits the act, or no admitted identity | no |
| 409 | `conflict` | the expected revision moved, or the act conflicts with current state | no |
| 409 | `operation_unknown` | the act was dispatched and its outcome is not confirmed | possibly; inspect the receipt before acting again |
| 422 | `request_refused` | the route refuses the act, with the reason | no |
| 422 | `invalid_evidence` | the act's evidence is refused, with the reason | no |
| 422 | `invalid_request` | the body does not match the API contract | no |
| 503 | `source_unavailable` | a source could not be read before dispatch (`Retry-After` set) | no |

`GET /api/operations/{operation_key}` returns a receipt's retained state, so an unknown outcome
can be checked without repeating the act.

## Reads and freshness

Snapshot reads (the fleet, the deliveries, a line's state, the maintenance and promotion state)
are served from the console's observations and make no call to GitHub. Content reads (a line's
tree, a file, a phase's substance) read GitHub on request through bounded readers. A read that
reports observed data carries `freshness`:

| Field | Carries |
| --- | --- |
| `state` | `loading`, `fresh`, `stale` or `unavailable` |
| `observed_at` | when the data was last observed successfully |
| `last_attempt_at` | when the console last tried |
| `reason_code` | why the state is not fresh, when it is not |
| `coverage` | how much of the expected data the observation covers |
| `age_seconds` | how old the observation is |

## Read next

- [Configuration](../configuration/)
- [The admission module](../../modules/admission/)
- [A command and its outcome](../../flows/command/)
