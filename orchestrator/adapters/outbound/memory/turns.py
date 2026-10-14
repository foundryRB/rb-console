"""In-memory turns, so long work is never awaited on the wire. A grounded co-pilot turn
runs a full model call (the driver shells out to `claude -p`, bounded at 180s) and the
fleet's forced rescan is dozens of GitHub reads across the org - both far longer than
the proxies in front of the pod hold a request open (oauth2-proxy's upstream default is
30s - the operator saw a bare "Error: 502" mid-turn, then again on the masthead's
refresh). So those endpoints start the work here in a daemon thread and hand back an id;
the SPA polls the result. The store is deliberately indifferent to what it runs: a turn
is a callable and its result dict, which is why the rescan (INT-FC-R107) could adopt the
chat turns' machinery (INT-FC-R55) whole rather than grow its own. Ephemeral by design -
the Console keeps no database, and a turn lost to a pod restart degrades to a clear error
on the next poll, never a hung chat or a silently dropped refresh."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable

_TTL_SECONDS = 15 * 60  # a finished turn lingers long enough to be polled, then goes


class TurnStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turns: dict[str, dict] = {}

    def start(self, fn: Callable[[], dict]) -> str:
        """Run fn in the background; the returned id is what a later poll redeems."""
        turn_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._prune()
            self._turns[turn_id] = {"at": time.monotonic(), "status": "running"}

        def run() -> None:
            try:
                update = {"status": "done", "result": fn()}
            except Exception as exc:  # noqa: BLE001  the error IS the turn's result
                update = {
                    "status": "error",
                    "error": str(exc).strip()[:600] or "the turn failed",
                }
            with self._lock:
                if (
                    turn_id in self._turns
                ):  # pruned mid-run: nobody is coming back for it
                    self._turns[turn_id].update(update)

        threading.Thread(target=run, daemon=True, name=f"turn-{turn_id}").start()
        return turn_id

    def poll(self, turn_id: str) -> dict:
        """The turn's current truth: running, its result dict (flattened), or its error.
        An unknown id is an error, not a hang - the pod may have restarted under the turn."""
        with self._lock:
            self._prune()
            turn = self._turns.get(turn_id)
            if turn is None:
                # Neutral copy: this surfaces in the chat AND in the masthead's refresh
                # status line, so it must not read as chat-only ("ask again") there.
                return {
                    "status": "error",
                    "error": "unknown turn - the console may have restarted; try again",
                }
            if turn["status"] == "done":
                return {"status": "done", **turn["result"]}
            if turn["status"] == "error":
                return {"status": "error", "error": turn["error"]}
            return {"status": "running"}

    def _prune(self) -> None:
        """Drop expired turns (called under the lock). Keeps the store from growing."""
        now = time.monotonic()
        for tid in [t for t, v in self._turns.items() if now - v["at"] > _TTL_SECONDS]:
            del self._turns[tid]
