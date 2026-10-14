"""A failed dispatch says what failed, safely, in the log, on its receipt and in the answer
(INT-FC-R190): the unknown outcome and a source-unavailable refusal each name the cause, so an
operator no longer has to read the pod to learn which source failed."""
from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_intent import intent

from orchestrator.adapters.inbound.http.errors import register_errors
from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
from orchestrator.application.services.operations.operation_admission import OperationAdmission
from orchestrator.application.services.operations.safe_reason import safe_reason
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext

CONTEXT = CommandContext("operator", "local", "grant", frozenset({"delivery.drive"}), frozenset({"org/app"}), "revision", "org")
SECRET = "ghp_" + "A" * 36


def _fail():
    try:
        raise OSError(f"https://x:{SECRET}@api.github.com/repos/org/app?access_token={SECRET} refused")
    except OSError as exc:
        raise SourceUnavailable("Studio REST response unavailable") from exc


@intent("INT-FC-R190")
def test_a_failed_dispatch_is_logged_recorded_and_answered_with_its_cause(tmp_path, caplog):
    store = OperationReceiptStore(tmp_path)
    admission = OperationAdmission(store)
    with caplog.at_level(logging.WARNING), pytest.raises(OperationUnknown) as caught:
        admission.execute(CONTEXT, "delivery.drive", "org/app", "op-1", {"repo": "org/app"}, _fail)
    reason = "SourceUnavailable: Studio REST response unavailable"
    assert caught.value.reason == reason
    assert reason in str(caught.value) and "inspect its receipt" in str(caught.value)
    receipt = store.get(caught.value.operation_key)
    assert receipt.state == "unknown"
    assert receipt.reason == f"dispatch_outcome_unconfirmed: {reason}"
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert reason in logged and "OSError" in logged
    assert SECRET not in logged + receipt.reason + str(caught.value)


@intent("INT-FC-R190")
def test_a_reason_never_carries_a_token_url_credentials_or_a_query():
    text = safe_reason(OSError(f"token {SECRET} at https://u:p@host/path?sig=abc and sk-ant-oat01-{'b' * 30}"))
    assert SECRET not in text and "u:p@" not in text and "sig=abc" not in text and "sk-ant-oat01" not in text
    assert text.startswith("OSError: token [redacted]")
    assert len(safe_reason(OSError("x" * 1000))) == 300


@intent("INT-FC-R190")
def test_a_cause_hidden_with_from_none_stays_hidden(tmp_path, caplog):
    def hidden():
        try:
            raise TimeoutError("claude -p --append-system-prompt <the transcript>")
        except TimeoutError:
            raise RuntimeError("Driver timed out after 90s") from None

    admission = OperationAdmission(OperationReceiptStore(tmp_path))
    with caplog.at_level(logging.WARNING), pytest.raises(OperationUnknown):
        admission.execute(CONTEXT, "delivery.drive", "org/app", "op-2", {"repo": "org/app"}, hidden)
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "Driver timed out after 90s" in logged and "transcript" not in logged


@intent("INT-FC-R190")
def test_the_answers_name_the_cause():
    app = FastAPI()
    register_errors(app)

    @app.get("/unavailable")
    def unavailable():
        raise SourceUnavailable("Studio REST response unavailable")

    @app.get("/unknown")
    def unknown():
        raise OperationUnknown("k" * 64, "SourceUnavailable: Studio REST response unavailable")

    client = TestClient(app)
    refused = client.get("/unavailable")
    assert refused.status_code == 503
    assert refused.json()["message"] == "The source is unavailable (Studio REST response unavailable). Its last observation may be stale."
    answered = client.get("/unknown")
    assert answered.status_code == 409 and answered.json()["operation_key"] == "k" * 64
    assert "its dispatch failed: SourceUnavailable: Studio REST response unavailable" in answered.json()["message"]
