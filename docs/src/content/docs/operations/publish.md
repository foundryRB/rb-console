---
title: Drive from the published console
id: DOC-FOUNDRY-CONSOLE-005
type: Guide
status: Active
updated: "2026-10-08"
summary: Watch, drive and take advice from the console published on the install, from any browser.
---

The console is published on the install, so any signed-in browser can watch a line end to end,
drive it, and ask its co-pilot. Your machine is only a driver; the compute, the tools and the state
live on the install.

## When to use

You want to start, drive or close a delivery, act on the maintenance loop, or promote a release,
without a set-up workstation.

## Steps

1. Sign in at the install's console host. The app realm admits operators from its existing users.
2. Pick a project on the Fleet page to open its cockpit. A project with no open line opens in its
   project view, where the act is opening a new line.
3. Before the first drive of a line, choose its model in the masthead: a saved agent and one of its
   models. The console seats that agent's credential for the line; nothing is committed.
4. Start or drive the line. The console checks the line's state, its gate and its configuration,
   and refuses with the reason when something is missing.
5. At an interactive gate, read the record and its review, ask the co-pilot if you want, then Sign
   or Re-drive with feedback.
6. On the Maintenance and Promotion tabs, drive the act the row names: resolve, review or merge a
   ticket; promote a release to a target.

## Verify

- The line card shows the phase you drove as running, then its record and gate as they land.
- The run band's logs follow the worker live; a finished run's logs stay readable.

## Read next

- [Drive a line by hand](../hand-drive/)
- [Configure the runtime settings](../runtime-settings/)
- [A one-shot line, ask to delivered](../../flows/one-shot-line/)
