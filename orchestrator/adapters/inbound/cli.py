"""``delivery`` CLI: the read-only, rung-0 face of the orchestrator core.

    python -m orchestrator status <repo>   # derived state, human-readable
    python -m orchestrator next <repo>     # just the next command

Deterministic and read-only: it derives, it never writes. It is the same
derivation the REST ``/api`` door exposes in the full service; a CLI is simply
another door onto the same core.
"""

from __future__ import annotations

import argparse
import sys

from orchestrator.application.ports.inbound.projections.read_local_delivery import (
    ReadLocalDeliveryPort,
)
from orchestrator.domain.delivery import AWAITING_GATE
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.delivery_state import DeliveryState

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        sys.stderr.write("stdout encoding remains unchanged\n")


def render(state: DeliveryState) -> str:
    lines = [f"delivery: {state.repo}", f"status:   {state.status}"]
    if state.phase:
        lines.append(f"phase:    {state.phase}")
    if state.gates:
        lines.append("gates:")
        for gate in state.gates:
            lines.append(
                f"  - {gate.name}: {gate.signed_on if gate.signed else 'PENDING'}"
            )
    if state.status == AWAITING_GATE:
        lines.append(
            f"blocked:  awaiting the {state.blocked_gate} gate (a human must sign)"
        )
    lines.append(f"next:     {state.next_command}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, reader: ReadLocalDeliveryPort) -> int:
    parser = argparse.ArgumentParser(
        prog="delivery",
        description="Derive a delivery's state from its committed .delivery/ scratch (read-only).",
    )
    parser.add_argument("command", choices=("status", "next"))
    parser.add_argument("repo", help="path to the delivery repo")
    args = parser.parse_args(argv)

    try:
        state = reader.execute(args.repo)
    except SourceUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(state.next_command if args.command == "next" else render(state))
    return 0
