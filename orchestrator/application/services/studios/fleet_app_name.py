"""Studios shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.identity.norm_slug import helper_norm_slug
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.domain.services.fleet.app_identity import _app_repo_slug


def helper_fleet_app_name(repo: str, *, studios: StudioGateway | None) -> str:
    """The fleet name of the app that ships from ``repo`` (its manifest entry, joined on
    the repository the way the fleet is), or "" when no onboarded app ships from it or
    the studio cannot answer."""
    if studios is None:
        return ""
    wanted = partial(helper_norm_slug)(partial(helper_slug)(repo))
    for app in studios.platform_apps():
        if (
            app.name
            and partial(helper_norm_slug)(_app_repo_slug(app)) == wanted
        ):
            return app.name
    return ""
