---
title: Deploy an install
id: DOC-FC-OPS-DEPLOY
type: Guide
status: Active
updated: "2026-10-08"
summary: Move an install to a console release - its deploy branch's chart pin and values, image promotion, and the checks after the sync.
---

Each install runs the console from its own deploy branch, `deploy-<install>`, in the console's
repository. Argo CD tracks the branch's `prod/` folder; the image updater moves the console's image
tags along semver and writes them back to `prod/values.yaml`. A release that changes the chart
reaches the install when its chart pin moves.

## When to use

A release changes the chart or the worker, or an install's values change.

## Steps

1. Confirm no run is mid-phase if the change replaces the worker or alters what a drive compiles;
   a console restart alone loses no run.
2. On the deploy branch, set `prod/Chart.yaml` to the release's chart version (the dependency and
   the chart's own version) and adjust `prod/values.yaml` under `foundry-console:`.
3. Set `images.worker.tag` to the release's version when the release changes the worker: the worker
   image runs only in launched pods, so lines pick it up at their next phase.
4. Commit as a fast-forward of the branch head you read.
5. Let Argo CD sync, or ask it to refresh the application.

## Verify

- The application reads Synced and Healthy at the commit you pushed.
- The console pod is ready (its first observation tick completed), and the board reads fresh.
- The images on the pod match the release.

## Read next

- [Back up the console](../back-up/)
- [Configuration](../../reference/configuration/)
