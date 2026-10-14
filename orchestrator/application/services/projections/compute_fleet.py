"""Projections shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.projections.list_deliveries import (
    ListDeliveriesPort,
)
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.identity.norm_slug import helper_norm_slug
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.projections.activity_by_repo import (
    helper_activity_by_repo,
)
from orchestrator.application.services.projections.activity_for import (
    helper_activity_for,
)
from orchestrator.domain.delivery import NOT_A_DELIVERY
from orchestrator.domain.fleet import CORE
from orchestrator.domain.model.fleet_item import FleetItem
from orchestrator.domain.model.platform_app import PlatformApp
from orchestrator.domain.model.repository_inventory_entry import (
    RepositoryInventoryEntry,
)
from orchestrator.domain.services.fleet.app_identity import _app_repo_slug


def helper_compute_fleet(
    *,
    platform_repo: str,
    source: DeliverySource | None,
    studios: StudioGateway | None,
    workflows: WorkflowRunner | None,
    cap_list_deliveries: ListDeliveriesPort,
) -> list[FleetItem]:
    """Join every org repo with the delivery index and platform-studio apps into the
    Fleet view: is it a delivery, is it onboarded, is it live. Pure over cached inputs."""
    deliveries = {d.repo: d for d in cap_list_deliveries.execute()}
    apps: dict[str, PlatformApp] = {}
    ek: set[str] = set()
    pp: set[str] = set()
    core: set[str] = {partial(helper_norm_slug)(platform_repo)}
    if studios is not None:
        for app in studios.platform_apps():
            if app.name:
                apps[partial(helper_norm_slug)(_app_repo_slug(app))] = app
        ek = {partial(helper_norm_slug)(slug) for slug in studios.estimatekit_slugs()}
        pp = {partial(helper_norm_slug)(slug) for slug in studios.protopane_slugs()}
        playbook = studios.playbook_repo()
        if playbook:
            core.add(partial(helper_norm_slug)(partial(helper_slug)(playbook)))
    repos: list[RepositoryInventoryEntry] = []
    if source is not None:
        repos = source.list_org_repos()
    acts, acts_known = partial(helper_activity_by_repo, workflows=workflows)()
    items: list[FleetItem] = []
    seen: set[str] = set()
    for r in repos:
        full = r.repository
        seen.add(full)
        name = r.name
        d = deliveries.get(full)
        is_del = d is not None and d.status != NOT_A_DELIVERY
        key = partial(helper_norm_slug)(name)
        app = apps.get(key)
        items.append(
            FleetItem(
                repo=full,
                name=name,
                is_delivery=is_del,
                delivery_status=d.status if is_del else None,
                delivery_phase=d.phase if is_del else None,
                onboarded=app is not None and app.onboarded,
                live=app.status if app else None,
                app_name=app.name if app else "",
                host=app.hostname
                if app
                else "",
                role=CORE if key in core else app.role if app else None,
                updated=r.updated_at,
                estimatekit=key in ek,
                protopane=key in pp,
                hidden="foundry-hidden" in r.topics,
                activity=partial(helper_activity_for)(d, full, acts, acts_known),
            )
        )
    for full, d in deliveries.items():
        if full not in seen and d.status != NOT_A_DELIVERY:
            slug = partial(helper_slug)(full)
            skey = partial(helper_norm_slug)(slug)
            items.append(
                FleetItem(
                    full,
                    slug,
                    True,
                    d.status,
                    d.phase,
                    False,
                    None,
                    None,
                    estimatekit=skey in ek,
                    protopane=skey in pp,
                    activity=partial(helper_activity_for)(d, full, acts, acts_known),
                )
            )
    return items
