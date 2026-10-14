"""An in-memory index of derived delivery states, refreshed from a source out of
band so the read path (list, status) never scans on the request. The whole-org scan
runs on a schedule in the background; a page load reads the warm cache.
"""

from __future__ import annotations

import threading

from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.domain.model.delivery_state import DeliveryState


class DeliveryIndex:
    def __init__(self) -> None:
        self._by_repo: dict[str, DeliveryState] = {}
        self._scanned = False
        self._versions: dict[str, int] = {}
        self._lock = threading.Lock()

    @property
    def scanned(self) -> bool:
        """False until the first refresh completes, so the UI can tell empty from cold."""
        return self._scanned

    def refresh(self, source: DeliverySource) -> int:
        """Rescan the source and replace the cache. Returns the delivery count."""
        with self._lock:
            versions = dict(self._versions)
        states = source.scan()
        with self._lock:
            replacement = {state.repo: state for state in states}
            for repo, state in self._by_repo.items():
                if self._versions.get(repo, 0) != versions.get(repo, 0):
                    replacement[repo] = state
            self._by_repo = replacement
            self._scanned = True
            return len(self._by_repo)

    def all(self) -> list[DeliveryState]:
        return list(self._by_repo.values())

    def get(self, repo: str) -> DeliveryState | None:
        return self._by_repo.get(repo)

    def put(self, state: DeliveryState) -> None:
        """Write one delivery's freshly derived state through to the cache, so a read
        right after a mutating act (sign, re-open) agrees with what the act changed.
        The background refresh remains the bulk truth; this only closes the gap between
        an act and the next scheduled rescan."""
        with self._lock:
            self._by_repo[state.repo] = state
            self._versions[state.repo] = self._versions.get(state.repo, 0) + 1
