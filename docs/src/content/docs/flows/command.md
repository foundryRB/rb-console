---
title: A command and its outcome
id: DOC-FC-FLOW-COMMAND
type: Flow
status: Active
updated: "2026-10-08"
summary: How one command is admitted, claimed, validated, dispatched and recorded, and what each outcome reads as in the cockpit.
---

Every mutation the console performs follows one path, from the operator's press (or a machine
caller's request) to a durable receipt. The path ends in exactly one of four outcomes the cockpit
names: complete, conflict, refused, or unknown.

## Sequence

```mermaid
sequenceDiagram
  autonumber
  actor U as Operator
  participant P as Sign-in proxy
  participant Wb as Web tier
  participant B as Backend
  participant R as Receipts
  participant Ow as Owner (GitHub, studio, executor)
  U->>P: POST with Idempotency-Key and If-Match
  P->>Wb: request with the admitted subject
  Wb->>B: request with the proxy secret and the identity
  B->>B: command context: principal, actions, repository scope
  B->>R: claim the operation key
  B->>B: validate fresh evidence and the expected revision
  B->>R: mark dispatched
  B->>Ow: the effect
  B->>R: complete with the result
  B-->>U: result, or 409 conflict, 4xx refusal, 409 operation_unknown
```

## Steps

1. The browser sends the command with an operation id (`Idempotency-Key`) and, where the command
   acts on a source revision, the revision it read (`If-Match`).
2. The sign-in proxy admits the operator; the web tier forwards the identity with the proxy secret.
   The backend builds the command context and checks the action and the repository against it.
3. The backend claims the operation's receipt atomically, under a key derived from the act's scope
   and its operation id. A key already completed returns its retained result; a key whose outcome
   is unknown answers unknown again and dispatches nothing.
4. It validates fresh evidence and the expected revision. A refusal here releases the claim: a
   moved revision answers 409 conflict, invalid evidence 422, a source that cannot be read 503. In
   each case nothing was done.
5. It records the dispatch, performs the effect, and completes the receipt with the result. From
   dispatch on, any failure answers 409 `operation_unknown` with the operation key, so the cockpit
   keeps the same operation id and offers to inspect the receipt before acting again.

## Read next

- [The admission module](../../modules/admission/)
- [API conventions](../../reference/api/)
- [Drive from the published console](../../operations/publish/)
