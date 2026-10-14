"""The canonical lifecycle payload: the one mapping between a definition and its JSON."""
from __future__ import annotations

import hashlib
import json

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.phase import Phase


def phase_fields(row: dict) -> dict:
    """The Phase arguments one canonical phase row carries."""
    if "artifact" not in row:
        raise ValueError("phase artifact must be explicit")
    return {
        "name": row["id"],
        "label": row["label"],
        "skill": row["skill"],
        "agent": row["agent"],
        "record": row["record"],
        "gate": row.get("gate") or "",
        "question": row["question"],
        "studio": row["studio"],
        "completion": row["completion"],
        "inputs": tuple(row["inputs"]),
        "artifact": row.get("artifact"),
        "tool": row["tool"],
    }


def decode_lifecycle(payload: dict) -> LifecycleDefinition:
    return LifecycleDefinition(
        payload["id"],
        payload["version"],
        tuple(Phase(**phase_fields(row)) for row in payload["phases"]),
        payload["schema_version"],
        str(payload.get("source_ref") or ""),
        str(payload.get("worker_image") or ""),
    )


def encode_lifecycle(definition: LifecycleDefinition) -> dict:
    return {
        "schema_version": definition.schema_version,
        "id": definition.id,
        "version": definition.version,
        "phases": [
            {
                "id": phase.name,
                "label": phase.label,
                "skill": phase.skill,
                "agent": phase.agent,
                "record": phase.record,
                "gate": phase.gate or None,
                "question": phase.question,
                "studio": phase.studio,
                "completion": phase.completion,
                "inputs": list(phase.inputs),
                "artifact": phase.artifact,
                "tool": phase.tool,
            }
            for phase in definition.phases
        ],
    }


def lifecycle_digest(definition: LifecycleDefinition) -> str:
    canonical = json.dumps(encode_lifecycle(definition), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def encode_pin(definition: LifecycleDefinition) -> dict:
    """The definition a line captures, as its configuration carries it."""
    return {
        **encode_lifecycle(definition),
        "source_ref": definition.source_ref,
        "digest": lifecycle_digest(definition),
        "worker_image": definition.worker_image,
    }


def decode_pin(pin: dict) -> LifecycleDefinition:
    """Read a line's captured definition, refusing a pin without its playbook revision or
    whose digest differs from its content."""
    try:
        definition = decode_lifecycle(pin)
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceUnavailable("line lifecycle pin is unavailable") from exc
    if not definition.source_ref:
        raise SourceUnavailable("line playbook revision is unavailable")
    if pin.get("digest") != lifecycle_digest(definition):
        raise SourceUnavailable("line lifecycle digest differs")
    return definition
