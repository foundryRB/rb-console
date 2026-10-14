---
title: Operate the execution door
id: DOC-FC-OPS-EXECUTION-DOOR
type: Guide
status: Active
updated: "2026-10-09"
summary: Enable the console's in-cluster execution door for the benchmark, seat its token, hand the caller its address, and rotate the token.
---

The execution door admits one machine caller, the benchmark, to the delivery-execution operations
on its own repositories. An install enables it in its chart values and seats its token out of band.

## When to use

An install runs the benchmark, or the door's token needs rotating.

## Steps

1. Create the token Secret in the console's namespace (for example `foundry-console-execution`,
   key `token`) with a long random value. Never print or commit the value.
2. Seat the same value in the caller's Secret, as its execution token.
3. On the install's deploy branch, set the door's values:
   `auth.execution.enabled: true`, `auth.execution.existingSecret` and `auth.execution.tokenKey`
   naming the Secret, `auth.execution.principal` (the caller's name), and
   `auth.execution.repositories` (for example `<owner>/bench-*`, under the installation's owner).
4. Let Argo CD sync, then give the caller its address,
   `http://<release>-execution.<namespace>.svc.cluster.local:8081`.
5. The caller sends `Authorization: Bearer <token>` on every request and an `Idempotency-Key` on
   every command, chooses its model by applying a saved install agent to the line, and drives without worker
   settings.
6. To rotate, replace the value in both Secrets and restart the console's pod.

## Verify

- From the caller's pod, `GET /api/agents` answers 200 with the token and 403 without it.
- A path outside the door, such as `/api/fleet`, answers 404; a repository outside the scope, 403.

## Read next

- [Sign out of the console](../sign-out/)
- [A bench delivery through the execution door](../../flows/bench-delivery/)
- [The admission module](../../modules/admission/)
