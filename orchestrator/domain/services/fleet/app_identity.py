"""Fleet identity and reported health rules."""
from __future__ import annotations

from orchestrator.domain.model.platform_app import PlatformApp

_HEALTHY_STATUS = 'running'

_UNHEALTHY_STATUSES = frozenset({'error', 'errored', 'failed', 'failing', 'unhealthy', 'degraded', 'crashloopbackoff', 'crashloop', 'crashing'})

def deployment_health(status: str) -> bool | None:
    """One platform status word folded to deployment health, fail-open: True only for a
    running app, False only for an EXPLICIT unhealthy word the platform names, and None for
    everything else - a paused app (deliberate), an absent/unknown signal, or an unrecognised
    word - so an unhealthy deployment is only ever derived from a real signal, never guessed."""
    word = (status or '').strip().lower()
    if word == _HEALTHY_STATUS:
        return True
    if word in _UNHEALTHY_STATUSES:
        return False
    return None

def _app_repo_slug(app: PlatformApp) -> str:
    """Declared repository slug for the fleet join."""
    return app.repository.rsplit("/", 1)[-1]
