from __future__ import annotations

import json

from orchestrator.adapters.outbound.events.event_payload import cloud_event, logger


class LoggingEventPublisher:
    """The publisher a console with no bus grant runs: states each fact to the log.

    Every act completes exactly as it would with a broker up, which is the
    one-way rule rather than a fallback. The envelope is still built, so a
    payload the bus would refuse is caught on the install that has no bus.
    """

    def publish(self, *, event_type: str, subject: str, data: dict[str, object]) -> None:
        try:
            cloud_event(event_type=event_type, subject=subject, data=data)
        except (TypeError, ValueError) as exc:
            logger.warning("dropped event %s: could not build envelope (%s)", event_type, exc)
            return
        logger.info("event %s %s %s", event_type, subject, json.dumps(data, default=str))
