import socket

from fastapi.testclient import TestClient
from pytest_intent import intent

from orchestrator.adapters.inbound.http.app import create_app


@intent("INT-FC-R145")
@intent("INT-FC-R190")
def test_source_failure_has_a_typed_response_and_bounded_retry_hint():
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

    app = create_app()
    secret = "ghp_" + "A" * 36

    @app.get("/source-failure")
    def unavailable():
        raise SourceUnavailable(f"repository identity is unavailable (token {secret})", retry_after=12)

    response = TestClient(app).get("/source-failure")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "12"
    assert response.json()["code"] == "source_unavailable"
    # The answer names which source failed, in its safe form: never a secret it carried.
    assert "repository identity is unavailable" in response.json()["message"]
    assert secret not in response.text


@intent("INT-FC-R13")
@intent("INT-FC-R168")
def test_openapi_exports_all_routes_without_sources(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("schema export reached the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    app = create_app()
    schema = app.openapi()
    operations = [operation for path in schema["paths"].values() for operation in path.values()]
    assert len(operations) == 69
    for path in schema["paths"].values():
        for operation in path.values():
            assert operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
            assert operation["responses"]["403"]["content"]["application/json"][
                "schema"
            ]["$ref"].endswith("ErrorResponse")
    assert create_app().openapi() == schema


@intent("INT-FC-R165")
def test_app_realm_identity_requires_trusted_proxy_provenance(monkeypatch):
    monkeypatch.setenv("FC_OIDC_ENABLED", "true")
    monkeypatch.setenv("FC_ORG", "org")
    monkeypatch.setenv("FC_OIDC_ISSUER", "https://identity.example/realm")
    monkeypatch.setenv("FC_PROXY_SECRET", "test-provenance-key")
    client = TestClient(create_app())
    for headers in [
        {},
        {"X-Auth-Request-User": "operator-1"},
        {"X-Console-Proxy-Secret": "test-provenance-key"},
        {"X-Auth-Request-User": "operator-1", "X-Console-Proxy-Secret": "incorrect"},
    ]:
        response = client.get("/api/config/session", headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"
    response = client.get(
        "/api/config/session",
        headers={
            "X-Auth-Request-User": "operator-1",
            "X-Console-Proxy-Secret": "test-provenance-key",
        },
    )
    assert response.status_code == 200
    assert response.json()["oidc_enabled"] is True
    assert client.get("/api/health").json() == {"status": "ok"}


@intent("INT-FC-R168")
def test_backend_has_no_static_mount():
    client = TestClient(create_app())
    assert client.get("/delivery").status_code == 404
    assert client.get("/assets/application.js").status_code == 404


@intent("INT-FC-R164")
def test_cold_metadata_routes_do_not_observe_or_mutate_sources(tmp_path, monkeypatch):
    from orchestrator.adapters.outbound.archives.operation_receipt_store import (
        OperationReceiptStore,
    )
    from orchestrator.application.services.operations.operation_admission import (
        OperationAdmission,
    )
    from orchestrator.container import build_capabilities

    class ForbiddenSource:
        def __getattr__(self, name):
            raise AssertionError(
                f"Metadata read reached source or mutation port: {name}"
            )

    monkeypatch.delenv("FC_OIDC_ENABLED", raising=False)
    forbidden = ForbiddenSource()
    capabilities = build_capabilities(
        forbidden,
        source=forbidden,
        msource=forbidden,
        psource=forbidden,
        workflows=forbidden,
        studios=forbidden,
        macts=forbidden,
        admission=OperationAdmission(OperationReceiptStore(tmp_path)),
    )
    client = TestClient(create_app(capabilities))
    paths = [
        "/api/deliveries",
        "/api/deliveries/state?repo=org/app",
        "/api/deliveries/overview?repo=org/app",
        "/api/fleet",
        "/api/studios",
        "/api/maintenance/state?repo=org/app",
        "/api/maintenance/inbox",
        "/api/promotion/state?repo=org/app",
        "/api/promotion/options?repo=org/app",
        "/api/runs",
        "/api/runs/graph?handle=workflow/example",
    ]
    for _ in range(3):
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.json()["freshness"]["state"] == "loading", path


@intent("INT-FC-R165")
def test_edge_context_qualifies_subject_and_retained_policy_checks(tmp_path, monkeypatch):
    import pytest
    from starlette.requests import Request

    from orchestrator.adapters.inbound.http.session import command_context
    from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
    from orchestrator.application.services.operations.delegated_grants import DelegatedGrants
    from orchestrator.domain.exceptions.permission_denied import PermissionDenied

    monkeypatch.setenv("FC_OIDC_ENABLED", "true")
    monkeypatch.setenv("FC_ORG", "org")
    monkeypatch.setenv("FC_REPOSITORIES", "org/app")
    monkeypatch.setenv("FC_OIDC_ISSUER", "https://identity.example/app-realm")
    monkeypatch.setenv("FC_PROXY_SECRET", "trusted-proxy")
    request = Request({"type": "http", "headers": [
        (b"x-auth-request-user", b"admitted-subject"),
        (b"x-console-proxy-secret", b"trusted-proxy"),
    ]})
    caller = command_context(request)
    assert caller.principal_id == "https://identity.example/app-realm#admitted-subject"
    caller.authorize("maintenance.drive", "org/app")
    with pytest.raises(PermissionDenied):
        caller.authorize("maintenance.drive", "org/other")
    store = OperationReceiptStore(tmp_path)
    grants = DelegatedGrants(store, caller.authorization_revision)
    grant = grants.issue(caller, "org/app", "run", 60)
    assert grants.resolve(grant["grant_id"], "org/app").principal_id == caller.principal_id
    for key, value in [
        ("FC_REPOSITORIES", "org/*"),
        ("FC_OIDC_ISSUER", "https://identity.example/other-realm"),
        ("FC_ORG", "other"),
        ("FC_OIDC_ENABLED", "false"),
    ]:
        with monkeypatch.context() as changed:
            changed.setenv(key, value)
            changed.setenv("FC_LOCAL_OPERATOR", "local-operator")
            if key == "FC_OIDC_ENABLED":
                changed.delenv("FC_PROXY_SECRET")
            local_request = Request({**request.scope, "client": ("127.0.0.1", 1)})
            current = command_context(local_request)
            with pytest.raises(PermissionDenied):
                DelegatedGrants(store, current.authorization_revision).resolve(
                    grant["grant_id"], "org/app"
                )
