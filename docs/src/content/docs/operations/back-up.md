---
title: Back up the console
id: DOC-FC-OPS-BACK-UP
type: Guide
status: Active
updated: "2026-10-08"
summary: Copy the console's two kinds of state - the archive volume, and the runtime settings and credentials in its namespace - and restore them.
---

The console keeps two kinds of state of its own. Its archive volume, mounted at `/data` on the
claim `<release>-data`, holds the operation receipts and the archived logs of terminal runs. Its
namespace holds the runtime settings and credentials as ConfigMaps and Secrets named `fc-*`:
saved agents, git identities and their role map, MCP door and pair credentials, each repository's
model selection, credential and repository binding. Everything else the console shows is derived
from GitHub, the studios and the executor.

## When to use

Before an upgrade that changes either kind of state, before moving the console, or on a schedule.

## Steps

1. Copy the archive volume out of the running pod:
   `kubectl exec <pod> -c foundry-console -- tar czf - -C /data . > console-archive.tgz`.
2. Export the runtime settings and credentials, without the fields the cluster assigns, so the
   file applies cleanly over the live objects or into an empty namespace:
   `kubectl get configmap,secret -n <namespace> -o json | jq '{apiVersion: "v1", kind: "List", items: [.items[] | select(.metadata.name | startswith("fc-")) | del(.metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.managedFields)]}' > console-settings.json`.
   The file holds secrets; store it as you store the install's other secrets.
3. Store both files where the install's other backups live.
4. To restore, pause the console on its deploy branch (`paused: true`) and let Argo CD scale it to
   zero.
5. Start a helper pod in the namespace that mounts the claim `<release>-data` at `/data`, copy
   `console-archive.tgz` into it, unpack it into `/data`, and delete the helper pod.
6. Apply the settings: `kubectl apply -n <namespace> -f console-settings.json`.
7. Unpause the console (`paused: false`) and let Argo CD start it.

## Verify

- `tar tzf console-archive.tgz` lists the receipts and run-log folders.
- `jq '.items | length' console-settings.json` counts the exported settings and credentials.
- After a restore, Settings lists the saved agents and identities, and the run history shows the
  archived runs.

## Read next

- [API conventions](../../reference/api/)
- [The admission module](../../modules/admission/)
