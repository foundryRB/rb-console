"""Decode authored fixture text before invoking the pure delivery resolver."""
from collections.abc import Mapping

from orchestrator.adapters.outbound.records.yaml_record_parser import (
    parse,
    parse_record,
)
from orchestrator.domain.model.delivery_record import DeliveryRecord
from orchestrator.domain.model.frontmatter import Frontmatter


def record_inputs(texts: Mapping[str, str]) -> dict[str, DeliveryRecord]:
    return {name: parse_record(text) for name, text in texts.items()}

def record_header(text: str) -> Frontmatter | None:
    return parse(text)
