"""Run the REST door with uvicorn. `python -m orchestrator.adapters.inbound.http.run`."""

from __future__ import annotations

import os

import uvicorn

from orchestrator.adapters.inbound.http.app import create_app
from orchestrator.adapters.inbound.http.log_config import log_config
from orchestrator.container import build_service

app = create_app(build_service())


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("FC_HOST", "127.0.0.1"),
        port=int(os.environ.get("FC_PORT", "8000")),
        log_config=log_config(),
    )


if __name__ == "__main__":
    main()
