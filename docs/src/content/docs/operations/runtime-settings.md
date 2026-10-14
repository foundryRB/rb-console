---
title: Configure the runtime settings
id: DOC-FC-OPS-RUNTIME-SETTINGS
type: Guide
status: Active
updated: "2026-10-08"
summary: Save the agents, git identities, MCP door credentials and home co-pilot a console needs before its workers can run.
---

Workers need a model credential, a git identity for their catalog agent, and credentials for the
studios' MCP doors. These are runtime settings edited in the console, stored in the cluster, and
applied without a redeploy.

## When to use

A new install, a new machine-user or model key, or a rotation of any of them.

## Steps

1. In Settings, save each agent the operators will choose from: a provider, its endpoint, the
   credential, and the models it serves.
2. Save a git identity for each machine-user (name, commit email, login and token), then assign one
   to each catalog agent and to the `console` role. An agent left unassigned has no identity and
   its steps cannot push.
3. Give the Reviewer a different identity from the Programmer, so its review can approve the
   Programmer's pull request.
4. Enter each MCP door's user and key. The list of doors is derived from the studios; you only fill
   it in.
5. Optionally pick the home co-pilot: a saved agent and one of its models.

## Verify

- Settings reports each secret as set without showing it.
- A drive passes its credential and identity checks.

## Read next

- [Operate the execution door](../execution-door/)
- [The settings module](../../modules/settings/)
