from __future__ import annotations

import asyncio
import contextlib
import queue
import threading

from orchestrator.adapters.outbound.events.event_payload import (
    _QUEUE_DEPTH,
    _RECONNECT_SECONDS,
    cloud_event,
    logger,
)


class NatsEventPublisher:
    """Implements EventPublisher over NATS, delivering on a background thread."""

    def __init__(self, *, servers: str, creds_path: str | None = None) -> None:
        self._servers = servers
        self._creds_path = creds_path
        self._queue: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=_QUEUE_DEPTH)
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def publish(self, *, event_type: str, subject: str, data: dict[str, object]) -> None:
        """State the fact and return. Never raises, never waits on delivery."""
        try:
            payload = cloud_event(event_type=event_type, subject=subject, data=data)
        except (TypeError, ValueError) as exc:
            logger.warning("dropped event %s: could not build envelope (%s)", event_type, exc)
            return
        self._ensure_worker()
        try:
            self._queue.put_nowait((event_type, payload))
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()  # drop the oldest, keep the newest
            logger.warning("event queue full (depth %d); dropped an older fact to admit %s", _QUEUE_DEPTH, event_type)
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait((event_type, payload))

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name="event-publisher", daemon=True)
            self._worker.start()

    def _run(self) -> None:
        try:
            asyncio.run(self._drain())
        except Exception as exc:  # noqa: BLE001  a dead worker must never escape
            logger.warning("event publisher worker stopped: %s", exc)

    async def _drain(self) -> None:
        try:
            import nats
        except ImportError:  # pragma: no cover  only when the dependency is absent
            logger.warning("nats-py is not installed; events will not be published")
            return
        connection = None
        loop = asyncio.get_running_loop()
        while True:
            event_type, payload = await loop.run_in_executor(None, self._queue.get)
            if connection is None or not connection.is_connected:
                try:
                    connection = await nats.connect(
                        servers=[s.strip() for s in self._servers.split(",") if s.strip()],
                        user_credentials=self._creds_path or None,
                        max_reconnect_attempts=-1,
                        reconnect_time_wait=_RECONNECT_SECONDS,
                    )
                except Exception as exc:  # noqa: BLE001  the bus may simply be down
                    logger.warning("dropped event %s: bus unreachable (%s)", event_type, exc)
                    continue
            try:
                # The subject IS the type, so a consumer's wildcard filter is the
                # type hierarchy itself.
                await connection.publish(event_type, payload)
            except Exception as exc:  # noqa: BLE001  never surfaced to a caller
                logger.warning("dropped event %s: publish failed (%s)", event_type, exc)
