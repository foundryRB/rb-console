"""Offline GitHub request counts, credential isolation and refusal behavior."""
from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from orchestrator.adapters.outbound.github.buffered_response import BufferedResponse
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.adapters.outbound.github.safe_redirect import SafeRedirect
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def test_conditional_reads_reuse_304_and_isolate_credentials() -> None:
    calls = []
    def open_request(request, timeout):
        calls.append(request)
        if request.get_header("If-none-match"):
            raise HTTPError(request.full_url, 304, "unchanged", {}, BytesIO())
        return BufferedResponse(b'{"name":"repo"}', {"ETag": '"v1"'}, 200)
    transport = GitHubTransport(opener=open_request)
    assert transport.json("https://api.github.com/repos/org/repo", "one") == {"name": "repo"}
    assert transport.json("https://api.github.com/repos/org/repo", "one") == {"name": "repo"}
    transport.json("https://api.github.com/repos/org/repo", "two")
    assert len(calls) == 3
    assert calls[1].get_header("If-none-match") == '"v1"'
    assert calls[2].get_header("If-none-match") is None
    assert transport.diagnostics()["cache_hits"] == 1


def test_complete_pagination_and_bounded_cycle() -> None:
    calls = []
    def open_request(request, timeout):
        calls.append(request.full_url)
        if "page=2" in request.full_url:
            return BufferedResponse(b'[2]', {}, 200)
        return BufferedResponse(b'[1]', {"Link": '<https://api.github.com/orgs/o/repos?page=2>; rel="next"'}, 200)
    transport = GitHubTransport(opener=open_request)
    assert transport.json("https://api.github.com/orgs/o/repos", "token", paginate=True) == [1, 2]
    assert len(calls) == 2
    with pytest.raises(SourceUnavailable):
        GitHubTransport(opener=open_request, max_pages=1).json("https://api.github.com/orgs/o/repos", "token", paginate=True)


@pytest.mark.parametrize("headers", [{"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}, {"Retry-After": "60"}])
def test_refusal_blocks_same_credential_without_more_requests(headers) -> None:
    calls = []
    def open_request(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 403, "refused", headers, BytesIO())
    transport = GitHubTransport(opener=open_request)
    for _ in range(2):
        with pytest.raises(SourceUnavailable):
            transport.json("https://api.github.com/user", "one")
    assert len(calls) == 1
    with pytest.raises(SourceUnavailable):
        transport.json("https://api.github.com/user", "two")
    assert len(calls) == 2
    assert "one" not in json.dumps(transport.diagnostics())


def test_background_reserves_command_headroom() -> None:
    calls = []
    def open_request(request, timeout):
        calls.append(request)
        return BufferedResponse(b'{}', {"x-ratelimit-remaining": "50"}, 200)
    transport = GitHubTransport(opener=open_request)
    transport.json("https://api.github.com/user", "token")
    with pytest.raises(SourceUnavailable):
        transport.json("https://api.github.com/user", "token", background=True)
    transport.json("https://api.github.com/user", "token")
    assert len(calls) == 2


def test_foreign_redirect_and_missing_credential_send_no_authorization() -> None:
    request = Request("https://api.github.com/user", headers={"Authorization": "Bearer secret"})
    with pytest.raises(SourceUnavailable):
        SafeRedirect().redirect_request(request, None, 301, "moved", {}, "https://foreign.example/user")
    calls = []
    transport = GitHubTransport(opener=lambda *args, **kwargs: calls.append(args))
    with pytest.raises(SourceUnavailable):
        transport.json("https://api.github.com/user", "")
    assert calls == []


def test_writes_are_attempted_once_and_immutable_blobs_reused() -> None:
    calls = []
    def open_request(request, timeout):
        calls.append(request)
        if request.get_method() == "POST":
            raise TimeoutError()
        return BufferedResponse(b'{}', {}, 200)
    transport = GitHubTransport(opener=open_request)
    url = "https://api.github.com/repos/o/r/git/blobs/" + "a" * 40
    transport.json(url, "token")
    transport.json(url, "token")
    with pytest.raises(SourceUnavailable):
        transport.request(Request("https://api.github.com/user", method="POST", headers={"Authorization": "Bearer token"}))
    assert len(calls) == 2


class Clock:
    def __init__(self):
        self.elapsed = 0.0
        self.waits = []
    def monotonic(self): return self.elapsed
    def time(self): return 1000 + self.elapsed
    def sleep(self, seconds): self.waits.append(seconds); self.elapsed += seconds


def scripted_transport(outcomes, **kwargs):
    calls = []
    clock = Clock()
    def open_request(request, timeout):
        calls.append((request.get_method(), timeout))
        value = outcomes.pop(0)
        if isinstance(value, Exception): raise value
        return value
    return GitHubTransport(opener=open_request, clock=clock, **kwargs), calls, clock


def refusal(status, headers=None):
    return HTTPError("https://api.github.com/user", status, "refused", headers or {}, BytesIO())


from pytest_intent import intent

@intent("INT-FC-R145")
def test_get_recovers_after_transient_network_and_server_failures():
    from urllib.error import URLError
    transport, calls, clock = scripted_transport([URLError("connection reset"), refusal(503), BufferedResponse(b'{"ok":true}', {}, 200)])
    assert transport.json("https://api.github.com/user", "token", timeout=1) == {"ok": True}
    assert len(calls) == 3
    assert clock.waits == [.1, .2]
    assert calls[0][1] > calls[1][1] > calls[2][1]

@intent("INT-FC-R145")
def test_exhaustion_is_bounded_and_reports_retry_hint():
    transport, calls, clock = scripted_transport([refusal(502), refusal(502), refusal(502)])
    with pytest.raises(SourceUnavailable) as raised:
        transport.json("https://api.github.com/user", "token")
    assert len(calls) == 3
    assert raised.value.retry_after > 0
    assert clock.waits == [.1, .2]

@intent("INT-FC-R145")
@pytest.mark.parametrize("status", [401, 403])
def test_permanent_auth_refusal_is_not_retried(status):
    transport, calls, clock = scripted_transport([refusal(status)])
    with pytest.raises(SourceUnavailable): transport.json("https://api.github.com/user", "token")
    assert len(calls) == 1 and clock.waits == []

@intent("INT-FC-R145")
@pytest.mark.parametrize("status", [403, 429])
def test_short_explicit_rate_limit_recovers_within_original_deadline(status):
    transport, calls, clock = scripted_transport([refusal(status, {"retry-after": ".5"}), BufferedResponse(b'{}', {}, 200)])
    assert transport.json("https://api.github.com/user", "token", timeout=1) == {}
    assert len(calls) == 2 and clock.waits == [.5]
    assert calls[1][1] == .5

@intent("INT-FC-R145")
def test_long_rate_defer_is_shared_only_with_same_credential():
    transport, calls, clock = scripted_transport([refusal(429, {"retry-after": "60"}), BufferedResponse(b'{}', {}, 200)])
    for token in ["one", "one"]:
        with pytest.raises(SourceUnavailable) as raised: transport.json("https://api.github.com/user", token)
        assert raised.value.retry_after == 60
    assert len(calls) == 1 and clock.waits == []
    assert transport.json("https://api.github.com/user", "two") == {}
    assert len(calls) == 2

@intent("INT-FC-R145")
def test_short_wait_that_exhausts_deadline_does_not_retry():
    transport, calls, clock = scripted_transport([refusal(429, {"retry-after": ".5"})])
    with pytest.raises(SourceUnavailable): transport.json("https://api.github.com/user", "token", timeout=.25)
    assert len(calls) == 1 and clock.waits == []

@intent("INT-FC-R145")
@pytest.mark.parametrize("status", [404, 409, 422])
def test_domain_http_answers_are_preserved_without_retry(status):
    transport, calls, clock = scripted_transport([refusal(status)])
    with pytest.raises(HTTPError) as raised: transport.json("https://api.github.com/user", "token")
    assert raised.value.code == status and len(calls) == 1 and clock.waits == []

@intent("INT-FC-R145")
@pytest.mark.parametrize("status", [503, 429])
def test_writes_are_never_retried_even_with_short_retry_after(status):
    transport, calls, clock = scripted_transport([refusal(status, {"retry-after": ".1"})])
    with pytest.raises(SourceUnavailable):
        transport.request(Request("https://api.github.com/user", method="POST", headers={"Authorization": "Bearer token"}))
    assert len(calls) == 1 and clock.waits == []


@intent("INT-FC-R174")
def test_the_transport_reports_its_request_mix_without_a_credential_or_a_url(caplog):
    """The periodic report keeps upstream requests, immutable reuse and conditional 304s apart,
    marks the scheduler's share, and names the lowest remaining budget, never a token or URL."""
    import logging

    clock = Clock()
    def open_request(request, timeout):
        if request.get_header("If-none-match"):
            raise HTTPError(request.full_url, 304, "unchanged", {"X-RateLimit-Remaining": "4321"}, BytesIO())
        remaining = "1200" if "tok-second" in request.get_header("Authorization") else "4320"
        return BufferedResponse(b'{"ok":1}', {"ETag": '"v1"', "X-RateLimit-Remaining": remaining}, 200)
    transport = GitHubTransport(opener=open_request, clock=clock, report_every=60)
    blob = "https://api.github.com/repos/org/secret-repo/git/blobs/" + "a" * 40
    with caplog.at_level(logging.INFO, logger="orchestrator.adapters.outbound.github.github_transport"):
        transport.json("https://api.github.com/repos/org/secret-repo", "tok-secret")
        transport.json("https://api.github.com/repos/org/secret-repo", "tok-secret")
        transport.json(blob, "tok-secret")
        transport.json(blob, "tok-secret")
        with transport.background_scope():
            transport.json("https://api.github.com/repos/org/other", "tok-secret")
        assert caplog.records == []
        clock.elapsed += 61
        transport.json(blob, "tok-secret")
        assert len(caplog.records) == 1
        transport.json(blob, "tok-secret")
        assert len(caplog.records) == 1
        clock.elapsed += 61
        transport.json("https://api.github.com/repos/org/third", "tok-second")
    first, second = (record.getMessage() for record in caplog.records)
    assert first.startswith("GitHub transport over 61s: 4 requests (1 background), 2 immutable reuses, 1 not modified, 0 refusals")
    assert "lowest remaining budget 4320 across the 1 credentials that reported one" in first
    assert second.startswith("GitHub transport over 61s: 1 requests (0 background), 1 immutable reuses, 0 not modified, 0 refusals")
    assert "lowest remaining budget 1200 across the 2 credentials that reported one" in second
    assert "secret" not in first + second and "tok-" not in first + second
    counts = transport.diagnostics()
    assert (counts["requests"], counts["immutable_reuses"], counts["not_modified"], counts["cache_hits"]) == (5, 3, 1, 4)


def test_a_transport_without_a_reporting_interval_is_refused():
    with pytest.raises(ValueError):
        GitHubTransport(report_every=0)


@intent("INT-FC-R174")
def test_the_served_process_writes_the_transport_report_to_its_log():
    """Uvicorn configures only its own loggers; the served process adds the console's, so the
    report reaches the log instead of being dropped below the default WARNING threshold."""
    import subprocess
    import sys
    from pathlib import Path

    emit = ("import logging, logging.config\n"
            "{configure}"
            "logging.getLogger('orchestrator.adapters.outbound.github.github_transport').info('GitHub transport over 300s: probe')\n")
    configure = ("from orchestrator.adapters.inbound.http.log_config import log_config\n"
                 "logging.config.dictConfig(log_config())\n")
    def stderr(script):
        return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parents[1]).stderr
    assert "probe" not in stderr(emit.format(configure=""))
    assert "GitHub transport over 300s: probe" in stderr(emit.format(configure=configure))
