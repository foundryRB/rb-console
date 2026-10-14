"""Delivery shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.studios.fleet_app_name import (
    helper_fleet_app_name,
)
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.demo_source import DemoSource


def helper_demo_source(
    repo: str, state: DeliveryState, *, studios: StudioGateway | None
) -> DemoSource | None:
    """The demo directive's facts for a line the source read as a demo (REF-Demo): the
    source repository, its app's fleet name, and this line's - the demo's own manifest
    entry when it is already onboarded, else ``demo-`` and the source app's name."""
    if not state.demo_of:
        return None
    source_app = partial(helper_fleet_app_name, studios=studios)(
        state.demo_of
    ) or partial(helper_slug)(state.demo_of)
    demo_app = (
        partial(helper_fleet_app_name, studios=studios)(repo) or f"demo-{source_app}"
    )
    return DemoSource(repo=state.demo_of, app=source_app, demo_app=demo_app)
