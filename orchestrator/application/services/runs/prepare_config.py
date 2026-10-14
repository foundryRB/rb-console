"""Resolve live target selection before admitting worker effects."""
from dataclasses import replace

from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.settings.identity_refs import (
    helper_identity_refs,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.agent_access import refuse_foreign_seat


def prepare_config(repo, requested: RunConfig, *, config, credentials, incarnations, context):
    """The run's configuration over the target's live selection, refused when the line
    runs on an agent the caller may not drive (another person's personal seat, or anything
    but an install agent through the execution door)."""
    if config is None or credentials is None:
        raise SourceUnavailable("worker settings are unavailable")
    identity = incarnations.verify_current(repo)
    selection = config.get_setting("target-" + helper_slug(repo)) or {}
    refuse_foreign_seat(selection, context)
    cfg = replace(requested, mode=RunMode.INTERACTIVE,
        worker_provider=selection.get("provider") or requested.worker_provider,
        worker_base_url=selection.get("base_url") or requested.worker_base_url,
        worker_model=selection.get("model") or requested.worker_model,
        worker_timeout_seconds=int(selection.get("timeout_seconds") or requested.worker_timeout_seconds))
    if cfg.worker_timeout_seconds < 600:
        raise ValueError("worker timeout must be at least 600 seconds")
    if not cfg.repo_target or not cfg.repo_rights:
        raise ValueError("repository target and write rights are required")
    if not cfg.worker_credential and not credentials.has_delivery(helper_slug(repo)):
        raise ValueError("no worker credential is configured")
    return cfg, identity

def prepare_agents(agents, *, studios, config, roles):
    if studios is None or config is None:
        raise SourceUnavailable("worker identities and catalog are unavailable")
    catalog = {agent.name: agent for agent in studios.agent_catalog()}
    identities = {}
    for agent in agents:
        if agent not in catalog:
            raise SourceUnavailable("required worker catalog agent is unavailable")
        name = roles.get(agent, "")
        refs = helper_identity_refs(name, config=config)
        if refs is None:
            raise ValueError("required worker git identity is not configured: " + agent)
        identities[agent] = refs
    return identities, catalog
