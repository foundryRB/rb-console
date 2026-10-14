"""Read complete YAML frontmatter from a delivery record's leading fence."""
from __future__ import annotations

from datetime import date, datetime

import yaml

from orchestrator.domain.model.delivery_record import DeliveryRecord
from orchestrator.domain.model.frontmatter import Frontmatter


def _date(value: object) -> str:
    """A canonical calendar date is exactly YYYY-MM-DD."""
    if isinstance(value, datetime):
        return ""
    text = str(value)
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return ""
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError):
        return ""
    return text if parsed.isoformat() == text else ""


def _fields(text: str) -> dict[str, object] | None:
    """Decode only a leading YAML fence, once at the external-format boundary."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        return None
    try:
        parsed = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _frontmatter(parsed: dict[str, object]) -> Frontmatter:
    body = {str(key).lower(): str(value) if value is not None else "" for key, value in parsed.items()}

    try:
        attempt = int(body.get("attempt", "0") or "0")
    except ValueError:
        attempt = 0
    return Frontmatter(
        status=body.get("status", "").lower(),
        phase=body.get("phase", ""),
        skill=body.get("skill", ""),
        gate=body.get("gate", ""),
        signed_on=_date(parsed.get("signed", "")),
        signed=bool(_date(parsed.get("signed", ""))),
        reviewed=bool(_date(parsed.get("reviewed", ""))),
        run=body.get("run", ""),
        attempt=attempt,
        mode=body.get("mode", "").lower(),
        credential_ref=body.get("credential_ref", ""),
        learned=_date(parsed.get("learned", "")),
        stamp_refused=body.get("stamp_refused", "").strip(),
    )


def parse(text: str) -> Frontmatter | None:
    fields = _fields(text)
    return _frontmatter(fields) if fields is not None else None


def parse_record(text: str) -> DeliveryRecord:
    """Decode once into the immutable facts consumed by sources and workers."""
    fields = _fields(text)
    if fields is None:
        return DeliveryRecord()
    return DeliveryRecord(frontmatter=_frontmatter(fields))
