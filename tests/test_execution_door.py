"""The execution door: one configured machine caller, by bearer token, in-cluster only, for
the delivery-execution operations alone, on its own repositories (INT-FC-R173)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from capability_support import make_capabilities
from fastapi.testclient import TestClient
from pytest_intent import intent
from starlette.requests import Request
from test_http import FakeRepos

from orchestrator.adapters.inbound.http.app import create_app
from orchestrator.adapters.inbound.http.session import (
    EXECUTION_ACTIONS,
    EXECUTION_ROUTES,
    command_context,
)
from orchestrator.application.ports.inbound.command_actions import COMMAND_ACTIONS
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext

ROOT = Path(__file__).resolve().parents[1]
DOOR = {"X-Console-Door": "execution", "X-Console-Proxy-Secret": "trusted-proxy"}
BEARER = {"Authorization": "Bearer machine-token"}


@pytest.fixture
def door_env(monkeypatch):
    monkeypatch.setenv("FC_OIDC_ENABLED", "true")
    monkeypatch.setenv("FC_ORG", "org")
    monkeypatch.setenv("FC_OIDC_ISSUER", "https://identity.example/app-realm")
    monkeypatch.setenv("FC_PROXY_SECRET", "trusted-proxy")
    monkeypatch.setenv("FC_EXECUTION_TOKEN", "machine-token")
    monkeypatch.setenv("FC_EXECUTION_PRINCIPAL", "foundry-benchmark")
    monkeypatch.setenv("FC_EXECUTION_REPOSITORIES", "org/bench-*")


def request(method: str, path: str, headers: dict[str, str], query: str = "") -> Request:
    return Request({
        "type": "http", "method": method, "path": path, "query_string": query.encode(),
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    })


@intent("INT-FC-R173")
def test_the_door_admits_its_caller_as_a_machine_with_execution_actions_only(door_env):
    caller = command_context(request("POST", "/api/deliveries/drive", {**DOOR, **BEARER}))
    assert caller.principal_id == "execution#foundry-benchmark"
    assert caller.initiator_kind == "machine"
    assert caller.allowed_actions == EXECUTION_ACTIONS == frozenset({
        "delivery.establish", "settings.apply_delivery", "settings.target", "delivery.configure",
        "settings.delivery_timeout", "delivery.drive", "delivery.close",
    })
    assert EXECUTION_ACTIONS < set(COMMAND_ACTIONS.values())
    for action in sorted(EXECUTION_ACTIONS):
        caller.authorize(action, "org/bench-7")
    for action in sorted(set(COMMAND_ACTIONS.values()) - EXECUTION_ACTIONS):
        with pytest.raises(PermissionDenied):
            caller.authorize(action, "org/bench-7")
    for repository in ("org/app", "org/benchmark", "other/bench-7"):
        with pytest.raises(PermissionDenied):
            caller.authorize("delivery.drive", repository)
    with pytest.raises(PermissionDenied):
        caller.authorize("delivery.drive")


@intent("INT-FC-R173")
@pytest.mark.parametrize("headers", [
    {**DOOR},
    {**DOOR, "Authorization": "Bearer wrong-token"},
    {**DOOR, "Authorization": "Basic machine-token"},
    {**DOOR, "X-Console-Proxy-Secret": "forged", **BEARER},
    {"X-Console-Door": "execution", **BEARER},
    {**DOOR, "X-Console-Door": "other", **BEARER},
    {**DOOR, "X-Auth-Request-User": "operator-1", "Authorization": "Bearer wrong-token"},
])
def test_the_door_refuses_without_its_verified_path_and_token(door_env, headers):
    with pytest.raises(PermissionDenied):
        command_context(request("POST", "/api/deliveries/drive", headers))


@intent("INT-FC-R173")
@pytest.mark.parametrize("scope", ["benchorg/*", "org/bench-*,other/bench-*", "*", "bench-*"])
def test_a_scope_outside_the_installation_owner_refuses_every_request(door_env, monkeypatch, scope):
    """Every effect resolves a target by name under the installation's owner, so a scope
    under another owner would act on the installation's own repositories."""
    monkeypatch.setenv("FC_EXECUTION_REPOSITORIES", scope)
    with pytest.raises(PermissionDenied):
        command_context(request("POST", "/api/deliveries/drive", {**DOOR, **BEARER}))


@intent("INT-FC-R173")
def test_a_non_ascii_bearer_is_refused_not_an_error(door_env):
    with pytest.raises(PermissionDenied):
        command_context(request("POST", "/api/deliveries/drive", {**DOOR, "Authorization": "Bearer töken"}))


@intent("INT-FC-R173")
def test_door_reads_of_a_line_are_scoped_to_the_callers_repositories(door_env):
    assert command_context(request("GET", "/api/deliveries/state", {**DOOR, **BEARER}, "repo=org/bench-3"))
    for query in ("repo=org/app", "repo=other/bench-3", "repo=org%2Fapp"):
        with pytest.raises(PermissionDenied):
            command_context(request("GET", "/api/deliveries/config", {**DOOR, **BEARER}, query))


@intent("INT-FC-R173")
def test_a_machine_drive_names_no_worker_settings_and_a_machine_establish_carries_the_ask_alone(door_env, tmp_path):
    """The machine caller runs on the agent applied to the line, so the console's stored
    credential only ever reaches that agent's own endpoint; it seeds its repository itself."""
    from orchestrator.domain.model.run_config import RunConfig
    service = make_capabilities(FakeRepos(tmp_path))
    caller = command_context(request("POST", "/api/deliveries/drive", {**DOOR, **BEARER}))
    for overrides in ({"worker_base_url": "https://collector.example"}, {"worker_model": "other"},
                      {"worker_provider": "opencode"}, {"worker_credential": "key"}):
        config = RunConfig(**{"worker_credential": None, "repo_target": "org/bench-1", "repo_rights": True, **overrides})
        with pytest.raises(PermissionDenied, match="names no worker settings"):
            service.drive.execute("org/bench-1", config, "run", context=caller, operation_id="op")
    for extra in ({"source": b"archive"}, {"source_name": "seed"}, {"app_name": "other-app"}):
        with pytest.raises(PermissionDenied, match="ask alone"):
            service.establish.execute("org/bench-1", "the ask", context=caller, operation_id="op", **extra)


@intent("INT-FC-R173")
@pytest.mark.parametrize("unset", ["FC_EXECUTION_TOKEN", "FC_EXECUTION_PRINCIPAL", "FC_EXECUTION_REPOSITORIES"])
def test_an_unconfigured_door_refuses_every_request(door_env, monkeypatch, unset):
    monkeypatch.setenv(unset, "")
    with pytest.raises(PermissionDenied):
        command_context(request("POST", "/api/deliveries/drive", {**DOOR, **BEARER}))


@intent("INT-FC-R173")
@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/api/fleet"), ("POST", "/api/agents"), ("POST", "/api/deliveries/model"),
    ("POST", "/api/deliveries/sign"), ("POST", "/api/runs/stop"), ("GET", "/api/runs/logs"),
    ("DELETE", "/api/agents/x"), ("POST", "/api/agents/x/apply-driver"), ("GET", "/api/establish"),
])
def test_the_door_serves_the_execution_operations_alone(door_env, method, path):
    with pytest.raises(PermissionDenied):
        command_context(request(method, path, {**DOOR, **BEARER}))


@intent("INT-FC-R173")
def test_requests_through_the_door_are_admitted_by_its_rule_over_http(door_env, tmp_path):
    client = TestClient(create_app(make_capabilities(FakeRepos(tmp_path))))
    assert client.get("/api/agents", headers={**DOOR, **BEARER}).status_code == 200
    refused = client.get("/api/agents", headers={**DOOR, "Authorization": "Bearer wrong-token"})
    assert refused.status_code == 403
    assert refused.json()["message"] == "An admitted execution caller is required."
    assert client.get("/api/fleet", headers={**DOOR, **BEARER}).status_code == 403
    outside = client.post(
        "/api/deliveries/config",
        json={"target": "org/app", "mode": "one-shot"},
        headers={**DOOR, **BEARER, "Idempotency-Key": "op-1"},
    )
    assert outside.status_code == 403
    inside = client.post(
        "/api/deliveries/config",
        json={"target": "org/bench-1", "mode": "one-shot"},
        headers={**DOOR, **BEARER, "Idempotency-Key": "op-2"},
    )
    assert inside.status_code == 200, inside.json()


@intent("INT-FC-R173")
def test_the_door_rule_applies_whatever_the_operator_gate(door_env, monkeypatch, tmp_path):
    monkeypatch.delenv("FC_OIDC_ENABLED")
    client = TestClient(create_app(make_capabilities(FakeRepos(tmp_path))))
    assert client.get("/api/agents", headers={**DOOR, "Authorization": "Bearer wrong-token"}).status_code == 403
    assert client.get("/api/agents", headers={**DOOR, **BEARER}).status_code == 200


@intent("INT-FC-R173")
def test_repository_scope_admits_owner_prefix_entries():
    context = CommandContext("principal", "operator", "grant", frozenset({"a"}),
                             frozenset({"org/bench-*", "org/app", "solo/*"}), "rev", "org")
    for repository in ("org/bench-1", "ORG/Bench-22", "org/app", "solo/anything"):
        context.authorize("a", repository)
    for repository in ("org/apps", "org/bench", "other/bench-1", "solos/x"):
        with pytest.raises(PermissionDenied):
            context.authorize("a", repository)


def _door_server(config: str) -> str:
    start = config.index("listen ${CONSOLE_BIND}:8081;")
    return config[config.rindex("server {", 0, start):]


@intent("INT-FC-R173")
def test_the_web_tier_door_forwards_the_bearer_and_serves_only_the_execution_routes():
    config = (ROOT / "devops/web.conf.template").read_text(encoding="utf-8")
    main, door = config[: config.index(_door_server(config))], _door_server(config)
    assert 'proxy_set_header Authorization "";' in main
    assert "X-Console-Door" not in main
    assert "proxy_pass_request_headers off;" in door
    assert "proxy_set_header Authorization $http_authorization;" in door
    assert "proxy_set_header X-Console-Door execution;" in door
    assert "X-Auth-Request-User" not in door and "x_forwarded" not in door
    assert "location / { return 404; }" in door
    routed = re.compile(re.search(r"location ~ (\^\S+\$) \{", door).group(1))
    served = ["/api/establish", "/api/agents", "/api/agents/Rafael%20Claude/apply-delivery",
              "/api/deliveries/config", "/api/deliveries/timeout", "/api/deliveries/drive",
              "/api/deliveries/state", "/api/deliveries/close", "/api/runs/status"]
    for path in served:
        assert routed.fullmatch(path), path
        assert any(route.fullmatch(path) for _method, route in EXECUTION_ROUTES), path
    for path in ("/api/fleet", "/api/agents/x", "/api/agents/x/apply-driver", "/api/deliveries/model",
                 "/api/deliveries/sign", "/api/runs/logs", "/api/runs/stop", "/api/establishx"):
        assert not routed.fullmatch(path), path
        assert not any(route.fullmatch(path) for _method, route in EXECUTION_ROUTES), path


def rendered(*values: str) -> list[dict]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to verify the rendered chart")
    arguments = [helm, "template", "console", str(ROOT / "k8s"), "--set", "githubOwner=example",
                 "--set", "docs.enabled=false", "--set", "images.worker.tag=1.2.3"]
    for value in values:
        arguments += ["--set", value]
    output = subprocess.run(arguments, check=True, capture_output=True, text=True).stdout
    return [item for item in yaml.safe_load_all(output) if item]


@intent("INT-FC-R173")
def test_the_chart_publishes_the_door_in_cluster_only_when_enabled():
    enabled = rendered("auth.execution.enabled=true", "auth.execution.existingSecret=console-execution",
                       "auth.execution.principal=foundry-benchmark", "auth.execution.repositories=org/bench-*")
    services = {item["metadata"]["name"]: item for item in enabled if item["kind"] == "Service"}
    door = services["console-execution"]
    assert door["spec"]["type"] == "ClusterIP"
    assert door["spec"]["ports"] == [{"name": "execution", "port": 8081, "targetPort": "execution"}]
    route = next(item for item in enabled if item["kind"] == "HTTPRoute")
    assert {ref["name"] for rule in route["spec"]["rules"] for ref in rule["backendRefs"]} == {"console"}
    deployment = next(item for item in enabled if item["kind"] == "Deployment")
    containers = {item["name"]: item for item in deployment["spec"]["template"]["spec"]["containers"]}
    assert {"name": "execution", "containerPort": 8081} in containers["web"]["ports"]
    env = {item["name"]: item for item in containers["foundry-console"]["env"]}
    token = env["FC_EXECUTION_TOKEN"]["valueFrom"]["secretKeyRef"]
    assert token == {"name": "console-execution", "key": "token", "optional": True}
    assert env["FC_EXECUTION_PRINCIPAL"]["value"] == "foundry-benchmark"
    assert env["FC_EXECUTION_REPOSITORIES"]["value"] == "org/bench-*"

    disabled = rendered()
    assert [item["metadata"]["name"] for item in disabled if item["kind"] == "Service"] == ["console"]
    deployment = next(item for item in disabled if item["kind"] == "Deployment")
    for container in deployment["spec"]["template"]["spec"]["containers"]:
        assert all(port.get("containerPort") != 8081 for port in container.get("ports", []))
        assert not any(item["name"].startswith("FC_EXECUTION") for item in container.get("env", []))
