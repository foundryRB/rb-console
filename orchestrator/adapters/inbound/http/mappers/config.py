from __future__ import annotations


def driver_dto(cfg) -> dict:
    """Serialise the driver config for the door. The api_key is never included; only
    ``configured`` reports whether one is set.
    """
    return {
        "base_url": cfg.base_url,
        "model": cfg.model,
        "configured": cfg.configured,
        "agent": cfg.agent,
    }


def config_dto(config: dict) -> dict:
    """The target-level config door shape: mode (interactive|one-shot), the per-target model
    selection (the saved agent that backs it + provider/base_url/model chosen on it), the worker's
    wall-clock budget in hours, and whether its credential is persisted (never the value)."""
    secs = config.get("timeout_seconds", 3600) or 3600
    return {
        "mode": config.get("mode", "interactive"),
        "provider": config.get("provider", "claude"),
        "base_url": config.get("base_url", ""),
        "model": config.get("model", ""),
        "agent": config.get("agent", ""),
        "agent_level": config.get("agent_level", ""),
        "agent_owner": config.get("agent_owner_label") or config.get("agent_owner", ""),
        "timeout_hours": round(secs / 3600, 2),
        "credentialed": config.get("credentialed", False),
    }
