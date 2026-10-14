"""The served process's log configuration: uvicorn's own, with the console's loggers beside it."""

from __future__ import annotations

import copy

from uvicorn.config import LOGGING_CONFIG


def log_config() -> dict:
    """Uvicorn configures only its own loggers, so without this the console's INFO lines (the
    transport's request report, the facts a console with no bus states) never reach the log."""
    config = copy.deepcopy(LOGGING_CONFIG)
    config["loggers"]["orchestrator"] = {"handlers": ["default"], "level": "INFO", "propagate": False}
    return config
