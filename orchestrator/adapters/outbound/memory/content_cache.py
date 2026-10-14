"""Thread safe LRU content cache with explicit size and time bounds."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict


class MemoryContentCache:
    def __init__(
        self,
        entries: int = 128,
        max_bytes: int = 4 * 1024 * 1024,
        ttl_seconds: float = 60,
    ) -> None:
        self._entries = entries
        self._max_bytes = max_bytes
        self._ttl = ttl_seconds
        self._values: OrderedDict[tuple[str, str, str], tuple[float, int, object]] = (
            OrderedDict()
        )
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str, str]) -> object | None:
        with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            if time.monotonic() - item[0] > self._ttl:
                self._values.pop(key)
                self._bytes -= item[1]
                return None
            self._values.move_to_end(key)
            return deepcopy(item[2])

    def put(self, key: tuple[str, str, str], value: object) -> None:
        size = len(json.dumps(value, default=asdict).encode())
        if size > self._max_bytes:
            return
        with self._lock:
            old = self._values.pop(key, None)
            if old:
                self._bytes -= old[1]
            self._values[key] = (time.monotonic(), size, deepcopy(value))
            self._bytes += size
            while len(self._values) > self._entries or self._bytes > self._max_bytes:
                _, removed = self._values.popitem(last=False)
                self._bytes -= removed[1]
