"""Rendered deployment boundaries and workflow permissions."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def rendered(oidc: bool) -> list[dict]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to verify the rendered chart")
    output = subprocess.run(
        [helm, "template", "console", str(ROOT / "k8s"), "--set", "githubOwner=example",
         "--set", f"auth.oidc.enabled={str(oidc).lower()}", "--set", "docs.enabled=false",
         "--set", "images.worker.tag=1.2.3"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [item for item in yaml.safe_load_all(output) if item]


@pytest.mark.parametrize("oidc", [True, False])
def test_web_tier_owns_the_public_socket_and_backend_is_loopback(oidc: bool) -> None:
    objects = rendered(oidc)
    deployment = next(item for item in objects if item["kind"] == "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    backend = next(item for item in containers if item["name"] == "foundry-console")
    env = {item["name"]: item for item in backend["env"]}
    assert env["FC_HOST"]["value"] == "127.0.0.1"
    assert "FC_PROXY_SECRET" in env
    assert "FC_OIDC_ISSUER" in env
    web = next(item for item in containers if item["name"] == "web")
    assert web["ports"] == [{"name": "web", "containerPort": 8080}]
    assert backend["readinessProbe"]["httpGet"]["port"] == web["ports"][0]["containerPort"]
    assert "127.0.0.1:8000/api/health" in " ".join(backend["livenessProbe"]["exec"]["command"])
    service = next(item for item in objects if item["kind"] == "Service")
    assert service["spec"]["ports"][0]["targetPort"] == ("oidc" if oidc else "web")
    if oidc:
        proxy = next(item for item in containers if item["name"] == "oauth2-proxy")
        assert "--upstream=http://127.0.0.1:8080" in proxy["args"]
        assert "--skip-auth-strip-headers=false" in proxy["args"]
    config = next(item for item in objects if item["kind"] == "ConfigMap")
    assert set(config["metadata"]) <= {"name", "namespace", "labels", "annotations"}
    assert config["data"]["FC_WORKER_IMAGE"] == "ghcr.io/example/foundry-console-worker:1.2.3"


def test_rendered_console_role_grants_workflow_runner_operations() -> None:
    role = next(item for item in rendered(True) if item["kind"] == "Role" and item["metadata"]["name"] == "console")
    workflow = next(rule for rule in role["rules"] if "workflows" in rule["resources"])
    assert {"create", "get", "list", "watch", "patch", "update", "delete"} <= set(workflow["verbs"])


def test_proxy_discards_incoming_authority_headers_and_accepts_loopback_identity() -> None:
    config = (ROOT / "devops/web.conf.template").read_text(encoding="utf-8")
    assert "proxy_pass_request_headers off;" in config
    assert 'default "";' in config
    assert "127.0.0.1 $http_x_forwarded_user;" in config
    assert "proxy_set_header X-Auth-Request-User $console_user;" in config
    assert 'proxy_set_header X-Console-Proxy-Secret "${CONSOLE_PROXY_SECRET}";' in config
    assert "proxy_set_header Idempotency-Key $http_idempotency_key;" in config
    assert "proxy_set_header If-Match $http_if_match;" in config


@pytest.mark.parametrize("oidc", [True, False])
def test_every_probe_port_resolves_on_its_own_container(oidc: bool) -> None:
    """The kubelet resolves a named probe port against the probed container's own ports only."""
    for item in rendered(oidc):
        if item["kind"] != "Deployment":
            continue
        for container in item["spec"]["template"]["spec"]["containers"]:
            names = {port.get("name") for port in container.get("ports", [])}
            for probe in ("readinessProbe", "livenessProbe", "startupProbe"):
                for handler in ("httpGet", "tcpSocket"):
                    port = (container.get(probe) or {}).get(handler, {}).get("port")
                    if isinstance(port, str):
                        assert port in names, (item["metadata"]["name"], container["name"], probe, port)
