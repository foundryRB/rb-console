"""From dispatch on, a command's every failure answers an unknown outcome (INT-FC-R166)."""
from __future__ import annotations

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.archives.operation_receipt_store import (
    OperationReceiptStore,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext

CONTEXT = CommandContext("operator", "local", "grant", frozenset({"delivery.drive"}), frozenset({"org/app"}), "revision", "org")


class FailingReceipts(OperationReceiptStore):
    """A receipt store that claims and marks dispatch, then cannot record the outcome."""

    def complete(self, key, result):
        raise SourceUnavailable("database is locked")

    def unknown(self, key, reason):
        raise SourceUnavailable("database is locked")


@intent("INT-FC-R166")
def test_an_effect_whose_receipt_cannot_be_recorded_answers_unknown_not_unavailable(tmp_path):
    effects = []
    admission = OperationAdmission(FailingReceipts(tmp_path))
    with pytest.raises(OperationUnknown):
        admission.execute(CONTEXT, "delivery.drive", "org/app", "op-1", {"repo": "org/app"}, lambda: effects.append("run"))
    assert effects == ["run"]


@intent("INT-FC-R166")
def test_a_refusal_before_dispatch_still_reads_as_the_refusal(tmp_path):
    admission = OperationAdmission(OperationReceiptStore(tmp_path))

    def refuse():
        raise SourceUnavailable("the line cannot be read")

    with pytest.raises(SourceUnavailable):
        admission.execute(CONTEXT, "delivery.drive", "org/app", "op-2", {"repo": "org/app"}, lambda: None, validate=refuse)
