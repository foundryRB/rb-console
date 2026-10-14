"""Compose the CLI's local reader at the process entry point."""

from orchestrator.adapters.inbound.cli import main as cli_main
from orchestrator.container import build_local_reader


def main(argv: list[str] | None = None) -> int:
    return cli_main(argv, reader=build_local_reader())
