import subprocess
import urllib.error
from unittest.mock import Mock

import pytest

from orchestrator.adapters.outbound.agents.http_driver_agent import HttpDriverAgent
from orchestrator.adapters.outbound.credentials.k8s_credential_store import (
    K8sCredentialStore,
)
from orchestrator.adapters.outbound.settings.k8s_config_store import K8sConfigStore
from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


@pytest.mark.parametrize("store,method", [(K8sConfigStore, "get_secret"), (K8sCredentialStore, "get_delivery")])
@pytest.mark.parametrize("code,body", [(1, ""), (0, "malformed%"), (0, "/w==")])
def test_failed_secret_read_is_unavailable(monkeypatch, store, method, code, body):
    monkeypatch.setenv("FC_LIVE", "1")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], code, body, "credential-sentinel"))
    with pytest.raises(SourceUnavailable) as caught:
        getattr(store(), method)("sample")
    assert "credential-sentinel" not in str(caught.value)


@pytest.mark.parametrize("store,method", [(K8sConfigStore, "get_secret"), (K8sCredentialStore, "get_delivery")])
def test_successful_absent_secret_remains_absent(monkeypatch, store, method):
    monkeypatch.setenv("FC_LIVE", "1")
    def run(args, **kwargs):
        assert "--ignore-not-found" in args
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(subprocess, "run", run)
    assert getattr(store(), method)("sample") == ""


def test_secret_inventory_failure_cannot_clear_configuration(monkeypatch):
    monkeypatch.setenv("FC_LIVE", "1")
    replies = iter([subprocess.CompletedProcess([], 0, '{"items":[]}', ""), subprocess.CompletedProcess([], 1, "", "sensitive")])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: next(replies))
    with pytest.raises(SourceUnavailable):
        K8sConfigStore().list_settings("mcp-")


def test_unavailable_auth_does_not_send_anonymous_request(monkeypatch):
    config = Mock()
    config.get_setting.side_effect = SourceUnavailable("unavailable")
    network = Mock()
    monkeypatch.setattr("urllib.request.urlopen", network)
    with pytest.raises(SourceUnavailable):
        HttpStudioGateway(config)._post("protopane", {})
    network.assert_not_called()


def test_uncertain_write_does_not_retry_through_second_door(monkeypatch):
    gateway = HttpStudioGateway(None)
    monkeypatch.setattr("urllib.request.urlopen", Mock(side_effect=urllib.error.URLError(TimeoutError())))
    gateway._tool = Mock()
    with pytest.raises(SourceUnavailable):
        gateway.create_app_repo("sample", "Sample", "A delivery")
    gateway._tool.assert_not_called()


@pytest.mark.parametrize("body", [b"data: broken", b"[]", b""])
def test_malformed_studio_envelope_is_unavailable(body):
    with pytest.raises(SourceUnavailable):
        HttpStudioGateway._sse(body)


def test_driver_errors_do_not_echo_process_output(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 1, "prompt-sensitive", "credential-sensitive"))
    with pytest.raises(RuntimeError, match="Driver execution failed") as caught:
        HttpDriverAgent().chat("sensitive", [], credential="credential-sensitive")
    assert "sensitive" not in str(caught.value)


def test_missing_driver_is_unknown_validation(monkeypatch):
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=FileNotFoundError()))
    assert HttpDriverAgent().validate("credential") is None
