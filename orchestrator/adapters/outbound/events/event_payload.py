"""Publish this console's facts to the shared event bus, one way and never blocking.

REF-Events fixes the envelope (CloudEvents) and the rule (section 6: a publish
never blocks, slows, or fails the act that caused it). Both are built here rather
than taken from a shared package: the REF is the only shared artifact, every
producer owns its own outbound adapter (section 7), and the shape is small
enough to own. The console's own precedent is ADR-038: the layer that exists to
watch the system never becomes load-bearing inside it.

The shape: ``publish`` builds the envelope, puts it on a **bounded** queue, and
returns. A daemon worker thread owns the NATS connection and drains the queue. A
full queue drops the oldest fact and logs, because the REF forbids queueing into
unbounded memory and a bus is not the record of what happened anyway. Nothing is
retried inside the caller's latency budget and nothing is surfaced to the caller
as an error. The connection is made lazily on the worker thread, so an
unreachable broker costs one background reconnect loop and no startup path, and
``nats-py`` is imported inside the worker, so a console with no bus grant runs
the logging publisher and never touches the import.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

#: This console as one stable URI-reference, fixed for its lifetime. A consumer
#: checks provenance against it, so it does not track the hostname an install
#: happens to serve the console on.
SOURCE = "/foundry/foundry-console"

#: Deep enough to ride out a broker restart, shallow enough that an absent broker
#: costs a bounded amount of memory forever.
_QUEUE_DEPTH = 256
#: The worker waits this long between reconnect attempts. Slow on purpose: a bus
#: that is down is not an incident for this console.
_RECONNECT_SECONDS = 30.0


def cloud_event(*, event_type: str, subject: str, data: dict[str, object]) -> bytes:
    """One CloudEvent, JSON-encoded, ready to publish.

    ``id`` is unique per event because delivery is at-least-once and it is the
    consumer's dedupe key. ``time`` is when the fact became true, which is now:
    the publish happens after the act it describes has already committed. A
    ``data`` the encoder refuses raises here, before anything is queued, so the
    producer's own bug is logged by the caller and never half-sent.
    """
    return json.dumps(
        {
            "specversion": "1.0",
            "id": str(uuid.uuid4()),
            "source": SOURCE,
            "type": event_type,
            "subject": subject,
            "time": datetime.now(UTC).isoformat(),
            "datacontenttype": "application/json",
            "data": data,
        },
        separators=(",", ":"),
    ).encode("utf-8")
