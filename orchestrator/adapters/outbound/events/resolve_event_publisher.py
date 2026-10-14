from __future__ import annotations

import os

from orchestrator.adapters.outbound.events.logging_event_publisher import (
    LoggingEventPublisher,
)
from orchestrator.adapters.outbound.events.nats_event_publisher import (
    NatsEventPublisher,
)


def resolve_event_publisher() -> LoggingEventPublisher | NatsEventPublisher:
    """The publisher this install is configured for, or the logging one.

    ``FC_NATS_SERVERS`` names the bus the console's grant reached; unset means
    no grant, and the console states its facts to the log. ``FC_NATS_CREDS`` is
    the credentials file the chart assembles from the two halves the grant
    produced (the seed this console minted, the JWT the platform signed).
    """
    servers = os.environ.get("FC_NATS_SERVERS", "").strip()
    if not servers:
        return LoggingEventPublisher()
    return NatsEventPublisher(servers=servers, creds_path=os.environ.get("FC_NATS_CREDS") or None)
