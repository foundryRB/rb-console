"""Generate pure domain defaults from the pinned playbook definition."""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path
from pprint import pformat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.adapters.outbound.records.lifecycle_codec import (  # noqa: E402
    phase_fields,
)


def generate(root: Path) -> str:
    payload = json.loads((root / "devops/vendor/lifecycle.json").read_text(encoding="utf-8"))
    pin = json.loads((root / "devops/vendor/PINNED.json").read_text(encoding="utf-8"))
    with tarfile.open(root / "devops/vendor/playbook.tar.gz", "r:gz") as archive:
        skills = {Path(name).parent.name: name for name in archive.getnames() if name.endswith("/SKILL.md")}
    for phase in payload["phases"]:
        if phase["skill"] not in skills:
            raise ValueError("Lifecycle skill missing from pinned tree")
    phases = "".join(
        "        Phase(\n"
        + "".join(f"            {key}={value!r},\n" for key, value in phase_fields(row).items())
        + "        ),\n"
        for row in payload["phases"]
    )
    return ('"""Generated from devops/vendor/lifecycle.json by scripts/generate_lifecycle.py."""\n'
            'from .model.lifecycle_definition import LifecycleDefinition\n'
            'from .model.phase import Phase\n\n'
            'CURRENT_PLAYBOOK_REF = ' + repr(pin['ref']) + '\n\n' +
            'CURRENT_SKILL_PATHS = ' + pformat(skills, sort_dicts=True, width=100) + '\n\n' +
            'CURRENT_LIFECYCLE = LifecycleDefinition(\n'
            '    id=' + repr(payload["id"]) + ',\n'
            '    version=' + repr(payload["version"]) + ',\n'
            '    phases=(\n' + phases + '    ),\n'
            '    schema_version=' + repr(payload["schema_version"]) + ',\n'
            ')\n')


def generate_artifacts(root: Path) -> str:
    payload = json.loads((root / "devops/vendor/artifact-handlers.json").read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(item is not None and not isinstance(item, str) for item in payload):
        raise ValueError("invalid artifact handler catalog")
    return ('"""Generated from devops/vendor/artifact-handlers.json by scripts/generate_lifecycle.py."""\n'
            'SUPPORTED_ARTIFACTS: frozenset[str | None] = frozenset(' + repr(tuple(payload)) + ')\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    outputs = {
        root / "orchestrator/domain/current_lifecycle.py": generate(root),
        root / "orchestrator/domain/lifecycle_artifacts.py": generate_artifacts(root),
    }
    for output, rendered in outputs.items():
        if args.check:
            if not output.exists() or output.read_text(encoding="utf-8") != rendered:
                parser.error(f"generated lifecycle differs: {output.name}")
        else:
            output.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
