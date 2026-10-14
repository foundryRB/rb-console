"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode


def helper_with_delivery_config(
    repo: str, config: RunConfig, *, cap_delivery_config: DeliveryConfigPort
) -> RunConfig:
    """Overlay the delivery-level mode and model choice onto a run config, so the
    delivery's own settings are authoritative over whatever a request happened to carry."""
    dc = cap_delivery_config.execute(repo)
    return replace(
        config,
        mode=RunMode(dc["mode"]),
        worker_provider=dc["provider"] or config.worker_provider,
        worker_base_url=dc["base_url"] or config.worker_base_url,
        worker_model=dc["model"] or config.worker_model,
        worker_timeout_seconds=dc.get("timeout_seconds")
        or config.worker_timeout_seconds,
    )
