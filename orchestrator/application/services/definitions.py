"""Immutable execution labels and budgets."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REF_DELIVERY_DIGEST = "The REF-Delivery contract, distilled: a delivery is five phases - scope (proposal.md), design (design.md), intent+plan (handoff.md), build+ship (build.md), and learn, which codifies the run's lessons into their durable homes (REF/skill changes) and journals a summary; the operator then closes the line - tagging the scratch ref delivered/<slug>/P<n> and removing it - as a separate explicit act (the Close-line control), so an unattended learn never destroys the journal it wrote. Progress is never stored; it is derived from which records exist and from each record's frontmatter 'signed:' line - a dated stamp there IS the signed gate and 'pending' IS an open one, whatever the prose says. Interactive mode suspends each gate for the operator's signature; one-shot mode is the operator's standing pre-authorization, where the deterministic engine stamps a gate only after a fresh-eyes review of that record passes. Agents never sign gates. Workers read their phase skill from the run's immutable playbook payload, so its pinned policy governs the ones who act; you are the advisory co-pilot beside that line. Logs narrate the past: a worker's line about a gate (an attempt bump, 'signed: pending') describes its own attempt's write, made before any later signature, and a worker writing 'pending' with the operator signing afterwards is the designed order, not a contradiction. The record's current frontmatter is the present; it outranks every log line."

REF_MAINTENANCE_DIGEST = "The REF-Maintenance contract, distilled: maintenance is the 1-to-n loop - file (a real issue), triage (the inbox), resolve (branch, conventional commit referencing the ticket, PR), review (fresh eyes post findings ending exactly VERDICT: PASS or VERDICT: FAIL as the last line, or VERDICT: UNRECORDED when the reviewer is the PR's author or the merger: a complete review that records no verdict, so nothing merges or re-drives on it and the PR waits for an independent reviewer), ship (the pipeline cuts and promotes on merge - nobody's act), live (the closing keyword fires when the commit lands). The ceremony is chosen PER ACT: gated (the default - the operator merges over a PASS), one-shot (the ENGINE merges on the recorded PASS with green checks, under the operator's standing authorization for that drive), direct (a conventional commit on the default branch, no PR; never a repo's standing default). Nothing merges unreviewed; the reviewer is never the merger; a red CI blocks the merge in every mode; a review counts only from the repo's owner, a member or a collaborator, and one by the PR's author or the merger records nothing; agents never merge, and what a merge may land is the repo's own gate. State is DERIVED: the issue is intent, the PR is review, the tag and the deployment are shipping - no .maintenance/ file, no tracker copy, nothing stored."

_HEALTHY_STATUS = "running"

_UNHEALTHY_STATUSES = frozenset(
    {
        "error",
        "errored",
        "failed",
        "failing",
        "unhealthy",
        "degraded",
        "crashloopbackoff",
        "crashloop",
        "crashing",
    }
)

_MODES = frozenset({"interactive", "one-shot"})

_DEFAULT_TIMEOUT_SECONDS = 3600

_MIN_TIMEOUT_SECONDS = 600

_RETENTION_SETTING = "run-retention"

_TERMINAL_RUN_PHASES = ("Succeeded", "Failed", "Error", "Stopped")

_SNAPSHOT_TAIL_LINES = 5000

_RECEIPT_TICKS = 30

_CHECKS_TICKS = 30

_GITID = "gitid-"

_GIT_ROLES = "git-roles"

_CONSOLE_ROLE = "console"

_PAIR = "pair-"

_DEFAULT_PAIR_HOST = "github.com"

_AGENT = "agent-"

_TARGET = "target-"
