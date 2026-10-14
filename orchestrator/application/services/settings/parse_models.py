"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations


def helper_parse_models(fields: dict) -> list[str]:
    """An agent's selectable models: the stored newline-joined list, falling back to its
    single default model so a dropdown always offers at least that."""
    raw = fields.get("models", "") if isinstance(fields, dict) else ""
    models = [m.strip() for m in raw.splitlines() if m.strip()]
    if not models and fields.get("model"):
        models = [fields["model"]]
    return models
