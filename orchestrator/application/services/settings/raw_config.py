"""Read required line configuration through its authoritative source."""

from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def helper_raw_config(repo: str, *, source: DeliverySource | None) -> dict:
    if source is None:
        raise SourceUnavailable("Line configuration source unavailable")
    return source.read_config(repo)
