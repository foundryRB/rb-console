import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.archives.operation_receipt_store import (
    OperationReceiptStore,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext


def context():
    return CommandContext(
        "issuer:operator",
        "operator",
        "admission-1",
        frozenset({"maintenance.comment"}),
        frozenset({"org/app"}),
        "policy-1",
        "install-1",
    )


def test_delegated_grant_is_immutable_and_survives_restart(tmp_path):
    store = OperationReceiptStore(tmp_path)
    authority = {
        "principal_id": "operator",
        "repositories": ["org/app"],
        "expires_at": "2026-10-06",
    }
    store.save_grant("grant-1", authority)
    restarted = OperationReceiptStore(tmp_path)
    assert restarted.get_grant("grant-1") == authority
    assert restarted.get_grant("absent") is None
    restarted.save_grant("grant-1", dict(reversed(list(authority.items()))))
    with pytest.raises(Conflict):
        restarted.save_grant("grant-1", {**authority, "repositories": ["org/other"]})
    assert restarted.get_grant("grant-1") == authority


def test_unavailable_grant_store_fails_closed(tmp_path):
    store = OperationReceiptStore(tmp_path)
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TABLE delegated_grants")
    with pytest.raises(SourceUnavailable):
        store.get_grant("grant-1")
    with pytest.raises(SourceUnavailable):
        store.save_grant("grant-1", {"principal_id": "operator"})


@intent("INT-FC-R165")
def test_authority_checked_before_receipt_or_dispatch():
    class Unreachable:
        def claim(self, *args, **kwargs):
            pytest.fail("Receipt reached before authorization")

    admission = OperationAdmission(Unreachable())
    for caller in [
        replace(context(), principal_id=""),
        replace(context(), repositories=frozenset()),
        replace(context(), allowed_actions=frozenset()),
        replace(context(), expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        replace(context(), initiator_kind="scheduler"),
    ]:
        with pytest.raises(PermissionDenied):
            admission.execute(
                caller,
                "maintenance.comment",
                "org/app",
                "op",
                {},
                lambda: pytest.fail(),
            )
    with pytest.raises(PermissionDenied):
        admission.execute(
            context(),
            "maintenance.comment",
            "org/app",
            "op",
            {},
            lambda: None,
            current_authorization_revision="revoked",
        )


def test_context_copies_mutable_grants():
    actions = {"maintenance.comment"}
    caller = replace(context(), allowed_actions=actions)
    actions.add("settings.save")
    with pytest.raises(PermissionDenied):
        caller.authorize("settings.save")


@intent("INT-FC-R166")
def test_concurrent_claim_and_restart_dispatch_once(tmp_path):
    effects = []

    def invoke(_):
        admission = OperationAdmission(OperationReceiptStore(tmp_path))
        try:
            return admission.execute(
                context(),
                "maintenance.comment",
                "org/app",
                "op-1",
                {"body": "hello"},
                lambda: effects.append("sent") or {"comment_id": 42},
            )
        except OperationUnknown:
            return "pending"

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(invoke, range(20)))
    assert effects == ["sent"]
    assert invoke(0) == {"comment_id": 42}
    assert effects == ["sent"]
    with pytest.raises(Conflict):
        OperationAdmission(OperationReceiptStore(tmp_path)).execute(
            context(),
            "maintenance.comment",
            "org/app",
            "op-1",
            {"body": "changed"},
            lambda: pytest.fail(),
        )


@pytest.mark.parametrize("checkpoint", ["claim", "intent", "after_effect"])
@intent("INT-FC-R166")
def test_crash_never_replays_ambiguous_operation(tmp_path, checkpoint):
    store = OperationReceiptStore(tmp_path)
    admission = OperationAdmission(store)
    key = admission.key(context(), "maintenance.comment", "org/app", "op-1")
    if checkpoint == "after_effect":

        def lost_reply():
            raise ConnectionError("response lost after source accepted comment")

        with pytest.raises(OperationUnknown):
            admission.execute(
                context(), "maintenance.comment", "org/app", "op-1", {}, lost_reply
            )
    else:
        import hashlib

        store.claim(key, hashlib.sha256(b"{}").hexdigest(), authority={})
        if checkpoint == "intent":
            store.mark_dispatched(key, {"subject": "issue-1"})
    restarted = OperationAdmission(OperationReceiptStore(tmp_path))
    with pytest.raises(OperationUnknown):
        restarted.execute(
            context(),
            "maintenance.comment",
            "org/app",
            "op-1",
            {},
            lambda: pytest.fail("replayed"),
        )


@intent("INT-FC-R166")
def test_secret_write_has_no_secret_digest_or_result_and_rejects_replay(tmp_path):
    store = OperationReceiptStore(tmp_path)
    admission = OperationAdmission(store)
    secret = "private-test-token"
    assert admission.execute(
        context(),
        "maintenance.comment",
        "org/app",
        "secret-1",
        {"token": secret},
        lambda: {"token": secret},
        secret_write=True,
    ) == {"token": secret}
    with pytest.raises(Conflict):
        admission.execute(
            context(),
            "maintenance.comment",
            "org/app",
            "secret-1",
            {"token": secret},
            lambda: pytest.fail(),
            secret_write=True,
        )
    assert secret.encode() not in store.path.read_bytes()
    key = admission.key(context(), "maintenance.comment", "org/app", "secret-1")
    assert store.get(key).fingerprint == "secret-write"
    assert store.get(key).result is None


def test_unavailable_receipts_prevent_source_effect(tmp_path):
    store = OperationReceiptStore(tmp_path)
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TABLE receipts")
    with pytest.raises(SourceUnavailable):
        OperationAdmission(store).execute(
            context(), "maintenance.comment", "org/app", "op", {}, lambda: pytest.fail()
        )


def test_scopes_are_independent(tmp_path):
    admission = OperationAdmission(OperationReceiptStore(tmp_path))
    first = admission.key(context(), "maintenance.comment", "org/app", "id")
    assert first != admission.key(
        replace(context(), installation_id="elsewhere"),
        "maintenance.comment",
        "org/app",
        "id",
    )
    assert first == admission.key(
        replace(context(), grant_id="another"), "maintenance.comment", "org/app", "id"
    )


def test_receipt_completion_requires_dispatch(tmp_path):
    store = OperationReceiptStore(tmp_path)
    store.claim("key", "fingerprint", authority={})
    with pytest.raises(Conflict):
        store.complete("key", {"id": 1})
    store.mark_dispatched("key", {"expected_revision": "abc"})
    store.unknown("key", "response_lost")
    store.complete("key", {"id": 1})
    assert store.get("key").state == "completed"


@intent("INT-FC-R166")
def test_receipt_inspection_is_owner_scoped_and_hides_command_result(tmp_path):
    from orchestrator.application.use_cases.operations.inspect_operation import (
        InspectOperation,
    )

    admission = OperationAdmission(OperationReceiptStore(tmp_path))
    admission.execute(
        context(),
        "maintenance.comment",
        "org/app",
        "id",
        {},
        lambda: {"private": "content"},
    )
    key = admission.key(context(), "maintenance.comment", "org/app", "id")
    inspect = InspectOperation(admission)
    view = inspect.execute(key, context=context())
    assert view == {
        "operation_key": key,
        "state": "completed",
        "reason": "",
        "evidence": {"repository": "org/app"},
    }
    for actor in [
        replace(context(), principal_id="other"),
        replace(context(), repositories=frozenset()),
        replace(context(), installation_id="other"),
    ]:
        with pytest.raises(PermissionDenied):
            inspect.execute(key, context=actor)


@pytest.mark.parametrize("repository", ["org/app", ""])
@pytest.mark.parametrize("secret_write", [False, True])
@intent("INT-FC-R166")
def test_owner_can_inspect_claim_after_validation_crash_without_replay(
    tmp_path, repository, secret_write
):
    from orchestrator.application.use_cases.operations.inspect_operation import (
        InspectOperation,
    )

    actor = replace(context(), allowed_actions=frozenset({"runs.stop"}))
    admission = OperationAdmission(OperationReceiptStore(tmp_path))
    effects = []

    def process_dies():
        raise SystemExit("process ended during metadata validation")

    with pytest.raises(SystemExit):
        admission.execute(
            actor,
            "runs.stop",
            repository,
            "reserved",
            {"handle": "live/run"},
            lambda: effects.append("stopped"),
            validate=process_dies,
            secret_write=secret_write,
        )
    restarted = OperationAdmission(OperationReceiptStore(tmp_path))
    key = restarted.key(actor, "runs.stop", repository, "reserved")
    view = InspectOperation(restarted).execute(key, context=actor)
    assert view == {
        "operation_key": key,
        "state": "claimed",
        "reason": "",
        "evidence": {"repository": repository} if repository else {},
    }
    for unauthorized in (
        replace(actor, principal_id="another"),
        replace(actor, installation_id="another"),
        replace(actor, allowed_actions=frozenset()),
    ):
        with pytest.raises(PermissionDenied):
            InspectOperation(restarted).execute(key, context=unauthorized)
    with pytest.raises(Conflict if secret_write else OperationUnknown):
        restarted.execute(
            actor,
            "runs.stop",
            repository,
            "reserved",
            {"handle": "live/run"},
            lambda: effects.append("stopped"),
            secret_write=secret_write,
        )
    assert effects == []


def test_dispatch_retains_claim_authority_and_refines_proven_repository(tmp_path):
    from orchestrator.application.use_cases.operations.inspect_operation import (
        InspectOperation,
    )

    actor = replace(context(), allowed_actions=frozenset({"runs.stop"}))
    store = OperationReceiptStore(tmp_path)
    admission = OperationAdmission(store)
    key = admission.key(actor, "runs.stop", "", "reserved")
    authority = {
        "principal": actor.principal_id,
        "installation": actor.installation_id,
        "action": "runs.stop",
        "repository": "",
    }
    store.claim(key, "fingerprint", authority=authority)
    store.mark_dispatched(
        key, {"repository": "org/app", "authority": {"principal": "another"}}
    )
    restarted = OperationAdmission(OperationReceiptStore(tmp_path))
    assert restarted.receipts.get(key).evidence["authority"] == authority
    assert InspectOperation(restarted).execute(key, context=actor)["evidence"] == {
        "repository": "org/app"
    }
    with pytest.raises(PermissionDenied):
        InspectOperation(restarted).execute(
            key, context=replace(actor, repositories=frozenset())
        )
