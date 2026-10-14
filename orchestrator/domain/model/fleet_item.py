"""FleetItem domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FleetItem:
    repo: str  # org/name
    name: str  # short name (last path segment) - the REPOSITORY's, never the app's
    is_delivery: bool  # carries a live delivery line (its delivery/* scratch ref)
    delivery_status: str | None  # DeliveryState.status when a delivery, else None
    delivery_phase: str | None
    onboarded: bool  # registered + wired on the platform (manifest present)
    live: str | None  # platform app status: running / paused / unknown, else None
    updated: str | None  # ISO timestamp of the repo's last push, when known
    estimatekit: bool = False  # an estimatekit project exists for this slug
    protopane: bool = False  # a protopane prototype exists for this slug
    hidden: bool = False  # carries the 'foundry-hidden' repo topic (excluded by default)
    # The app's FLEET name, when this repo joined a platform app: the manifest key, and so
    # the namespace, the hostname label, the chart and the GHCR package prefix. A fact
    # distinct from `name` (INT-SKELETON-001); the two differ on any install whose
    # repositories are named for the organisation rather than the apps they hold.
    #
    # Every consumer that addresses the PLATFORM - pause/resume, the ArgoCD Application
    # link, the docs and Grafana URLs, the live host - must read this; every consumer that
    # addresses a DELIVERY-side studio (estimatekit, protopane) must read `name`. Without
    # the field a row carried only the repository's name, so all of them used it and were
    # wrong wherever the two diverge. Empty for a row that joined no app - a bare repo has
    # no fleet name - and callers fall back to `name`.
    app_name: str = ""
    # The app's public host, as its Gateway listener states it. Read, never derived: an app
    # on a short host serves there, and <app_name>.<domain> would advertise a dead route.
    host: str = ""
    # The row's ROLE. Two of the three values are the manifest's (ADR-032), read from the
    # joined platform app: 'parts' for an app that makes up the Foundry itself (console,
    # studios, library, ...) and 'output' for an app the Foundry built and runs.
    #
    # The third, 'core', is NOT a manifest role and never arrives on an app entry. It marks
    # the two repos the Foundry is built OUT OF rather than deployed AS: the platform repo
    # (foundry.yaml's `platform`) and the playbook (foundry.yaml's `playbook`). Neither can
    # ever be a parts row - INT-FOUNDRY-001 holds parts+output in exact bijection with the
    # teams/ folders, and neither has one: the platform chart is what renders those folders,
    # and the playbook ships no image at all. So the manifest declares them beside the app
    # lists rather than inside them, and the board needs its own word for that. Without it
    # both read as ordinary tenant repos, which is precisely how the substrate and the corpus
    # went invisible on a board that shows everything else the Foundry is made of.
    #
    # 'core' WINS over any manifest role. The two are structurally not apps, so an app entry
    # claiming one of these slugs is the anomaly, not the reason to demote the row.
    #
    # None when the repo is none of the above: a bare repo, or an in-flight delivery not yet
    # onboarded - those read as ordinary fleet, never as part of the platform.
    role: str | None = None
    # The LIVE-worker axis, read from the executor and orthogonal to delivery_status (which is
    # git-derived and cannot tell a working runner from a parked one): 'running' (a worker is
    # building now), 'suspended' (parked on a gate), 'idle' (executor reachable, nothing live).
    # None means UNKNOWN - no executor wired or unreachable - never idle, so the board never
    # implies a stopped runner it could not verify. Only a delivery ever carries it.
    activity: str | None = None
