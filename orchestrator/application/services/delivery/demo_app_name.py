"""Delivery shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.studios.fleet_app_name import (
    helper_fleet_app_name,
)
from orchestrator.domain.delivery import demo_source_name


def helper_demo_app_name(target: str, *, studios: StudioGateway | None) -> str:
    """The app name a demo line takes when the operator named none (REF-Demo section
    2): ``demo-`` followed by the source app's fleet name, which is ``demo-<x>`` (the
    repo's own name, the default anyway) wherever the source ships from a repo named
    for it. Only a ``demo-<x>`` target answers; every other target keeps the default."""
    source = demo_source_name(target)
    if not source:
        return ""
    source_app = partial(helper_fleet_app_name, studios=studios)(source)
    return f"demo-{source_app}" if source_app else ""
