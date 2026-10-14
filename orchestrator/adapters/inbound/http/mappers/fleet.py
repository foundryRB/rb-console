from __future__ import annotations


def fleet_dto(items, stale_since: str | None = None, stale_reason: str = "") -> dict:
    """The Fleet view: every project with its delivery, onboarding, and live status.

    ``stale_since`` carries the one fact the projects list cannot (INT-FC-R144): whether
    this board is current or held from before the org read started failing. Absent, the
    board is current - a caller that ignores the field reads it as fresh."""
    return {
        "stale_since": stale_since,
        "stale_reason": stale_reason if stale_since else "",
        "projects": [
            {
                "repo": i.repo,
                "name": i.name,
                "is_delivery": i.is_delivery,
                "delivery_status": i.delivery_status,
                "delivery_phase": i.delivery_phase,
                "onboarded": i.onboarded,
                "live": i.live,
                "updated": i.updated,
                "estimatekit": i.estimatekit,
                "protopane": i.protopane,
                "hidden": i.hidden,
                "role": i.role,
                "activity": i.activity,
                "app_name": i.app_name,
                "host": i.host,
            }
            for i in items
        ],
    }
