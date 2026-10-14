"""MCP JSON-RPC and tool refusals retain typed errors and unknown artifact truth."""
from pytest_intent import intent
import pytest
import urllib.error

from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway
from orchestrator.domain.exceptions.studio_tool_error import StudioToolError


def _gateway(monkeypatch, envelope: dict) -> HttpStudioGateway:
    """A gateway whose MCP POST returns the supplied SSE envelope."""
    import json

    gateway = HttpStudioGateway(config=None, domain="test.example")

    monkeypatch.setattr(gateway, "_initialize", lambda studio: "session")
    monkeypatch.setattr(
        gateway,
        "_post",
        lambda *a, **k: ("session", b"event: message\ndata: " + json.dumps(envelope).encode()),
    )
    return gateway


@intent("INT-FC-R115")
def test_a_jsonrpc_error_envelope_raises(monkeypatch):
    gateway = _gateway(
        monkeypatch,
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32603, "message": "PrFailedError: boom"}},
    )
    with pytest.raises(StudioToolError) as caught:
        gateway._tool("platform-studio", "create_app_repo", {"name": "x"})
    assert caught.value.error == "PrFailedError"
    assert "boom" in caught.value.detail


@intent("INT-FC-R115")
def test_an_iserror_result_raises_with_its_reason(monkeypatch):
    gateway = _gateway(
        monkeypatch,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "isError": True,
                "content": [
                    {"type": "text", "text": "AlreadyExistsError: repository gamma-app"}
                ],
            },
        },
    )
    with pytest.raises(StudioToolError) as caught:
        gateway._tool("platform-studio", "create_app_repo", {"name": "gamma-app"})
    assert caught.value.error == "AlreadyExistsError"
    assert caught.value.studio == "platform-studio"
    assert caught.value.tool == "create_app_repo"


@intent("INT-FC-R115")
def test_an_ordinary_result_still_parses(monkeypatch):
    """The regression guard's other half: raising on refusals must not turn a
    perfectly good answer into one."""
    gateway = _gateway(
        monkeypatch,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"structuredContent": {"name": "gamma-app", "branch": "main"}},
        },
    )
    assert gateway._tool("platform-studio", "create_app_repo") == {
        "name": "gamma-app",
        "branch": "main",
    }


@intent("INT-FC-R115")
def test_an_empty_read_is_not_a_refusal(monkeypatch):
    """A studio with nothing to report answers emptily and must NOT raise -
    an empty result and a refusal are different answers."""
    gateway = _gateway(monkeypatch, {"jsonrpc": "2.0", "id": 2, "result": {"content": []}})
    assert gateway._tool("platform-studio", "list_apps") == []


@intent("INT-FC-R115")
def test_a_refused_artifact_probe_reports_unknown_existence(monkeypatch):
    gateway = _gateway(
        monkeypatch,
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32603, "message": "down"}},
    )
    artifact = gateway._estimatekit('sample')
    assert artifact.reachable is False and artifact.exists is None


@intent("INT-FC-R116")
def test_unknown_studio_refusals_require_an_explicit_error_type():
    for detail in (
        "repository already exists: gamma-app",
        "repo creation needs the fleet write credential",
        "invalid app name 'SolveOS': must be a lowercase DNS label",
        "could not seed org/gamma-app; the repository was removed again",
    ):
        assert StudioToolError("platform-studio", "create_app_repo", detail).error == ""
    explicit = StudioToolError("platform-studio", "create_app_repo", "repository already exists", error_name="AlreadyExistsError")
    assert explicit.error == "AlreadyExistsError"


@intent("INT-FC-R115")
def test_mcp_tool_error_wrapper_preserves_the_named_refusal(monkeypatch):
    gateway = _gateway(monkeypatch, {
        "jsonrpc": "2.0", "id": 2,
        "result": {"isError": True, "content": [{"type": "text", "text": "Error executing tool create_app_repo: AlreadyExistsError: repository gamma-app"}]},
    })
    with pytest.raises(StudioToolError) as caught:
        gateway._tool("platform-studio", "create_app_repo", {"name": "gamma-app"})
    assert caught.value.error == "AlreadyExistsError"
    assert caught.value.detail == "AlreadyExistsError: repository gamma-app"
