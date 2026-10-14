"""Process-shared, bounded GitHub requests and credential budgets."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from threading import BoundedSemaphore, Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from orchestrator.adapters.outbound.github.buffered_response import BufferedResponse
from orchestrator.adapters.outbound.github.safe_redirect import SafeRedirect
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

_log = logging.getLogger(__name__)


class GitHubTransport:
    def __init__(self, *, workers: int = 4, queue_size: int = 32, cache_size: int = 1024, max_pages: int = 100, reserve: int = 100, opener=None, max_attempts: int = 3, max_retry_wait: float = 2, clock=None, report_every: float = 300) -> None:
        if not 1 <= max_attempts <= 5 or not 0 <= max_retry_wait <= 5:
            raise ValueError("GitHub retry bounds are invalid")
        if report_every <= 0:
            raise ValueError("GitHub report interval must be positive")
        self._max_attempts = max_attempts
        self._max_retry_wait = max_retry_wait
        self._clock = clock or time
        self._workers = BoundedSemaphore(workers)
        self._queue = BoundedSemaphore(queue_size)
        self._lock = Lock()
        self._cache: OrderedDict = OrderedDict()
        self._budgets: OrderedDict = OrderedDict()
        self._cache_size = cache_size
        self._max_pages = max_pages
        self._reserve = reserve
        self._opener = opener or build_opener(SafeRedirect()).open
        self._background = ContextVar("github_background", default=False)
        # requests: every request sent upstream, a 304 included; cache_hits: every answer served
        # from the cache, split into immutable_reuses (no request sent) and not_modified (a 304).
        self._counts = {"requests": 0, "background_requests": 0, "cache_hits": 0, "immutable_reuses": 0,
                        "not_modified": 0, "refusals": 0, "queued": 0}
        self._report_every = report_every
        self._reported = dict(self._counts)
        self._reported_at = self._clock.monotonic()

    def diagnostics(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def _report(self) -> None:
        """Log the request mix since the last report, at most once per interval: the counts and
        the lowest remaining primary budget across credentials, never a credential or a URL."""
        with self._lock:
            elapsed = self._clock.monotonic() - self._reported_at
            if elapsed < self._report_every:
                return
            delta = {name: self._counts[name] - self._reported[name] for name in self._counts if name != "queued"}
            budgets = [remaining for remaining, _ in self._budgets.values() if remaining is not None]
            self._reported, self._reported_at = dict(self._counts), self._clock.monotonic()
        _log.info(
            "GitHub transport over %ds: %d requests (%d background), %d immutable reuses, "
            "%d not modified, %d refusals; lowest remaining budget %s across the %d credentials that reported one",
            round(elapsed), delta["requests"], delta["background_requests"], delta["immutable_reuses"],
            delta["not_modified"], delta["refusals"], int(min(budgets)) if budgets else "unknown", len(budgets),
        )

    @contextmanager
    def background_scope(self):
        """Reserve command budget for all reads inside a scheduled observation."""
        marker = self._background.set(True)
        try:
            yield
        finally:
            self._background.reset(marker)

    def request(self, request: Request, timeout: float = 20, *, background: bool = False) -> BufferedResponse:
        background = background or self._background.get()
        deadline = self._clock.monotonic() + timeout
        if urlsplit(request.full_url).scheme != "https" or urlsplit(request.full_url).hostname != "api.github.com":
            raise SourceUnavailable("GitHub API authority refused")
        auth = request.get_header("Authorization") or ""
        if not auth:
            raise SourceUnavailable("GitHub credential unavailable")
        identity = hashlib.sha256(auth.encode()).digest()
        key = (identity, request.full_url, request.get_header("Accept"))
        read = request.get_method() == "GET"
        if not self._queue.acquire(blocking=False):
            raise SourceUnavailable("GitHub queue is full")
        with self._lock:
            self._counts["queued"] += 1
        acquired = False
        try:
            acquired = self._workers.acquire(timeout=max(0, deadline-self._clock.monotonic()))
            if not acquired:
                raise SourceUnavailable("GitHub queue deadline exceeded")
            if self._clock.monotonic() >= deadline:
                raise SourceUnavailable("GitHub request deadline exceeded")
            with self._lock:
                remaining, retry = self._budgets.get(identity, (None, 0))
                cached = self._cache.get(key) if read else None
                if cached:
                    self._cache.move_to_end(key)
                if background and remaining is not None and remaining <= self._reserve:
                    self._counts["refusals"] += 1
                    raise SourceUnavailable("GitHub budget deferred", retry_after=max(1, retry-self._clock.time()))
            if retry > self._clock.time():
                delay = retry-self._clock.time()
                if not read or not self._pause(delay, deadline):
                    with self._lock:
                        self._counts["refusals"] += 1
                    raise SourceUnavailable("GitHub budget deferred", retry_after=delay)
            if cached:
                body, headers = cached
                validator = headers.get("etag") or headers.get("last-modified")
                if validator:
                    request.add_header("If-None-Match" if headers.get("etag") else "If-Modified-Since", validator)
                if re.search(r"/git/(blobs|trees)/[0-9a-f]{40}(?:\?|$)", request.full_url):
                    with self._lock:
                        self._counts["cache_hits"] += 1
                        self._counts["immutable_reuses"] += 1
                    return BufferedResponse(body, headers, 200)
            for attempt in range(self._max_attempts if read else 1):
                if self._clock.monotonic() >= deadline:
                    raise SourceUnavailable("GitHub request deadline exceeded")
                with self._lock:
                    self._counts["requests"] += 1
                    if background:
                        self._counts["background_requests"] += 1
                try:
                    with self._opener(request, timeout=max(.001, deadline-self._clock.monotonic())) as response:
                        headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                        status = getattr(response, "status", 200)
                        body = response.read(2_000_001)
                    if len(body) > 2_000_000:
                        raise SourceUnavailable("GitHub response exceeds content bound")
                    break
                except HTTPError as exc:
                    headers = {str(k).lower(): str(v) for k, v in (exc.headers or {}).items()}
                    self._record(identity, headers, exc.code)
                    if exc.code == 304 and cached:
                        with self._lock:
                            self._counts["cache_hits"] += 1
                            self._counts["not_modified"] += 1
                        return BufferedResponse(cached[0], cached[1], 200)
                    rate_limited = self._rate_limited(headers, exc.code)
                    transient = exc.code >= 500 or rate_limited
                    delay = self._retry_delay(headers, rate_limited, attempt)
                    if read and transient and attempt+1 < self._max_attempts and self._pause(delay, deadline):
                        exc.close()
                        continue
                    if exc.code in (401, 403, 429) or exc.code >= 500:
                        raise SourceUnavailable(f"GitHub source refused ({exc.code})", retry_after=delay if transient else 30) from exc
                    raise
                except (URLError, TimeoutError, OSError) as exc:
                    delay = .1 * (2 ** attempt)
                    if read and attempt+1 < self._max_attempts and self._pause(delay, deadline):
                        continue
                    raise SourceUnavailable("GitHub source unavailable", retry_after=delay) from exc
            self._record(identity, headers, status)
            if read:
                with self._lock:
                    self._cache[key] = (body, headers)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
            return BufferedResponse(body, headers, status)
        finally:
            if acquired:
                self._workers.release()
            self._queue.release()
            with self._lock:
                self._counts["queued"] -= 1
            self._report()

    def _pause(self, delay: float, deadline: float) -> bool:
        """A retry consumes the same bounded request deadline."""
        if delay < 0 or delay > self._max_retry_wait or self._clock.monotonic()+delay >= deadline:
            return False
        self._clock.sleep(delay)
        return self._clock.monotonic() < deadline

    @staticmethod
    def _rate_limited(headers: dict[str, str], status: int) -> bool:
        return status == 429 or (status == 403 and ("retry-after" in headers or headers.get("x-ratelimit-remaining") == "0"))

    def _retry_delay(self, headers: dict[str, str], rate_limited: bool, attempt: int) -> float:
        try:
            if "retry-after" in headers:
                value = float(headers["retry-after"])
                return max(0, value) if math.isfinite(value) else 60
            if rate_limited:
                return max(0, float(headers.get("x-ratelimit-reset", self._clock.time()+60))-self._clock.time())
        except (TypeError, ValueError):
            return 60
        return .1 * (2 ** attempt)

    def _record(self, identity: bytes, headers: dict[str, str], status: int) -> None:
        def number(name: str, default: float) -> float:
            try:
                value = float(headers.get(name, default))
                return value if math.isfinite(value) else default
            except (ValueError, TypeError):
                return default
        with self._lock:
            previous_remaining, previous_retry = self._budgets.get(identity, (None, 0))
            remaining = number("x-ratelimit-remaining", -1 if previous_remaining is None else previous_remaining)
            retry = previous_retry if previous_retry > self._clock.time() else 0.0
            if remaining == 0:
                retry = number("x-ratelimit-reset", self._clock.time()+60)
            elif self._rate_limited(headers, status):
                retry = self._clock.time() + number("retry-after", min(300, max(60, previous_retry-self._clock.time())*2))
            self._budgets[identity] = (None if remaining < 0 else remaining, retry)
            self._budgets.move_to_end(identity)
            while len(self._budgets) > 128:
                self._budgets.popitem(last=False)

    def json(self, url: str, token: str, *, background: bool = False, paginate: bool = False, timeout: float = 20):
        deadline = self._clock.monotonic()+timeout
        result = []
        seen: set[str] = set()
        for _ in range(self._max_pages):
            if url in seen or self._clock.monotonic() >= deadline:
                raise SourceUnavailable("GitHub pagination deadline or cycle")
            seen.add(url)
            request = Request(url, headers={"Authorization": f"Bearer {token}" if token else "", "Accept": "application/vnd.github+json", "User-Agent": "foundry-console"})
            with self.request(request, max(.001, deadline-self._clock.monotonic()), background=background) as response:
                try:
                    data = json.load(response)
                except (ValueError, UnicodeError) as exc:
                    raise SourceUnavailable("GitHub returned invalid content") from exc
                link = response.headers.get("link", "")
            if not paginate or not isinstance(data, list):
                return data
            result.extend(data)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            if not match:
                return result
            url = match.group(1)
        raise SourceUnavailable("GitHub pagination exceeds page bound")
