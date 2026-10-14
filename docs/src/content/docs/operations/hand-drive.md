---
title: Drive a line by hand
id: DOC-FC-OPS-HAND-DRIVE
type: Guide
status: Active
updated: "2026-10-08"
summary: Run a whole delivery from a set-up workstation with the playbook's skills, the console optional and watching.
---

The console is optional: every phase runs by hand from a workstation with the playbook's delivery
skills, against the same studios and the same repository. You are the worker.

## When to use

You want to drive a phase interactively at a terminal, or the console is unavailable.

## Steps

1. Read the delivery flyer or `REF-Delivery` for the line's phases and gates.
2. Invoke the phase's delivery skill in a local Claude session. It drives the phase's studio and
   commits the scratch as it goes, on the line's `delivery/*` ref mounted at `.delivery/`.
3. Close each gate with the playbook's gate stamper, carrying your approval and the phase's review
   artifact.
4. Keep the cockpit open if you like; it shows the records as you push them.

## Verify

- The cockpit reads the phase and gate you closed, because it derives state from the records alone.

## Read next

- [Configure the runtime settings](../runtime-settings/)
- [The gate mechanism](../../reference/gates/)
