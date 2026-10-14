"""Ticket progress from observed reviews and repository-scoped runs."""

from __future__ import annotations

import re
from dataclasses import asdict

from orchestrator.domain.model.pr_position import PrPosition
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.maintenance_controls import derive_ticket_controls


def ticket_presentation(state: dict, runs: list[RunInventoryEntry]) -> dict:
    positions = state.get("positions") or {}
    lines, linked, closed, controls = {}, {}, {}, {}
    for issue in positions.get("issues", []):
        number = int(issue["number"])
        key = str(number)

        def matches(pr: dict, number: int = number) -> bool:
            return bool(
                re.search(rf"(^|/){number}-", pr.get("head", ""))
                and re.search(rf"#{number}(\D|$)", pr.get("title", ""))
            )

        pr = next((pr for pr in positions.get("prs", []) if matches(pr)), None)
        ended = (
            next((pr for pr in positions.get("recent_closed", []) if matches(pr)), None)
            if pr is None
            else None
        )
        run = next(
            (
                run
                for run in runs
                if run.repository == state.get("repo")
                and run.kind == "maintenance"
                and run.maintenance_act == "resolve"
                and str(run.ticket) == key
            ),
            None,
        )
        linked[key], closed[key] = pr, ended
        phase = run.phase if run else ""
        resolve_step, resolve_detail = "pending", "not driven"
        if run:
            if phase in {"Running", "Pending", "Suspended", "Stopping"}:
                resolve_step, resolve_detail = "current", "running"
            elif phase in {"Failed", "Error"}:
                resolve_step, resolve_detail = "failed", "failed"
            elif phase == "Succeeded":
                resolve_step, resolve_detail = "done", "ran"
            else:
                resolve_step, resolve_detail = "current", (phase or "driven").lower()
        review_step, review_detail = "pending", "-"
        review_hint = (
            "A gated or one-shot resolve opens a PR for its fresh-eyes review."
        )
        merge_step, merge_detail = "pending", "-"
        merge_hint = "Merge requires a recorded PASS and green checks."
        if pr:
            verdict = pr.get("verdict")
            review_step = (
                "done"
                if verdict == "pass"
                else "failed"
                if verdict == "fail"
                else "current"
            )
            review_detail = (
                str(verdict).upper()
                if verdict in {"pass", "fail"}
                else "unrecorded"
                if verdict == "unrecorded"
                else "awaiting"
            )
            review_hint = (
                f"PR #{pr['number']} is open and its review is UNRECORDED - it awaits an independent reviewer."
                if verdict == "unrecorded"
                else f"PR #{pr['number']} is open, awaiting a fresh-eyes verdict."
                if verdict not in {"pass", "fail"}
                else f"PR #{pr['number']}'s fresh-eyes review returned {review_detail}."
            )
            if verdict == "pass" and pr.get("checks") == "green":
                merge_step, merge_detail = "current", "ready"
                merge_hint = "PASS with green checks: ready to merge."
            else:
                merge_detail = "blocked"
                merge_hint = (
                    f"Merge blocked: verdict {verdict}, checks {pr.get('checks')}."
                )
        elif ended:
            merged = ended.get("state") == "merged"
            review_step, review_detail = (
                ("done", "merged") if merged else ("failed", "closed")
            )
            review_hint = (
                f"PR #{ended['number']} merged - reviewed and landed."
                if merged
                else "The PR was closed without merging - re-drive the ticket."
            )
            merge_step, merge_detail = (
                ("current", f"close #{number}") if merged else ("pending", "not merged")
            )
            merge_hint = f"PR merged - close #{number}." if merged else review_hint
        elif phase == "Succeeded":
            review_step, review_detail = "stalled", "verify"
            review_hint = "The resolve ran green but no open or recently closed PR is visible. Verify that work shipped before re-driving."
            merge_step, merge_detail = "current", "verify"
            merge_hint = "Confirm the PR merged and close the ticket, or re-drive if nothing shipped."
        cells = [
            (
                "ticket",
                "Ticket",
                "done",
                f"#{number} open",
                "The open issue: the intent record for this work.",
            ),
            (
                "resolve",
                "Resolve",
                resolve_step,
                resolve_detail,
                f"The resolve worker is {phase}."
                if run
                else "No resolve driven yet for this ticket.",
            ),
            ("review", "Review", review_step, review_detail, review_hint),
            ("merge", "Merge", merge_step, merge_detail, merge_hint),
        ]
        lines[key] = [
            {"key": k, "label": label, "step": step, "detail": detail, "hint": hint}
            for k, label, step, detail, hint in cells
        ]
        cells = lines[key]
        default_stop = next(
            (
                cell["key"]
                for cell in cells
                if cell["step"] in {"stalled", "failed", "current"}
            ),
            next(
                (cell["key"] for cell in reversed(cells) if cell["step"] != "pending"),
                "ticket",
            ),
        )
        controls[key] = asdict(
            derive_ticket_controls(
                PrPosition(**pr) if pr else None,
                PrPosition(**ended) if ended else None,
                run is not None,
                default_stop,
                "foundry-delivery-scale" in issue.get("labels", []),
                "foundry-wrong-repo" in issue.get("labels", []),
                (state.get("delivery") or {}).get("status") == "not-a-delivery",
            )
        )
    return {
        **state,
        "ticket_lines": lines,
        "linked_pr": linked,
        "closed_pr": closed,
        "ticket_controls": controls,
    }
