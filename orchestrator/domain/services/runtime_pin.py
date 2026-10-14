"""Select the installed runtime for a line whose playbook revision it executes."""

import re

from orchestrator.domain.current_lifecycle import CURRENT_PLAYBOOK_REF
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition


def worker_image_for(definition: LifecycleDefinition, installed_image: str) -> str:
    """A line launches on the installed worker image when the installation executes its
    pinned playbook revision; each submitted run records the image it ran. Each refusal is
    the line's or the installation's state, not a source that failed to answer, so it is
    a ValueError the operator reads as the reason."""
    if not definition.source_ref:
        raise ValueError("The line carries no lifecycle pin")
    if definition.source_ref != CURRENT_PLAYBOOK_REF:
        raise ValueError(
            "The line's pinned playbook revision has no compatible installed worker"
        )
    if not (
        re.search(r"@sha256:[0-9a-f]{64}$", installed_image)
        or re.search(r":v?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?$", installed_image)
    ):
        raise ValueError("The installed worker image is not versioned or digest-pinned")
    return installed_image
