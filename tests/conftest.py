"""Authority doubles for existing HTTP business mapping tests."""
from __future__ import annotations
from uuid import uuid4
import pytest
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from capability_support import UnitCommandContext
from orchestrator.application.ports.inbound.command_actions import COMMAND_ACTIONS


class BusinessHttpContext(UnitCommandContext):
    def authorize(self, action: str, repository: str = "", **kwargs) -> None:
        if action not in self.allowed_actions:
            raise PermissionDenied("The test authority did not grant this action")


@pytest.fixture(autouse=True)
def business_http_authority(request, monkeypatch):
    modules = {"test_agents", "test_establish_archive", "test_git_identities", "test_http",
               "test_maintenance_http", "test_pair_credentials", "test_promotion_declare",
               "test_promotion_drive", "test_promotion_http"}
    if request.module.__name__.rsplit(".", 1)[-1] not in modules:
        return
    from orchestrator.adapters.inbound.http import session
    monkeypatch.setattr(session, "command_context", lambda request: BusinessHttpContext(
        "http-business-operator", "local", "http-business-grant", frozenset(COMMAND_ACTIONS.values()),
        frozenset(), "http-business-authorization", "http-business-installation", admin=True))
    from starlette.testclient import TestClient
    original = TestClient.request

    def authorized_request(self, method, url, **kwargs):
        if method.lower() not in {"get", "head", "options"}:
            kwargs["headers"] = {**(kwargs.get("headers") or {}), "Idempotency-Key": uuid4().hex}
        return original(self, method, url, **kwargs)

    monkeypatch.setattr(TestClient, "request", authorized_request)
