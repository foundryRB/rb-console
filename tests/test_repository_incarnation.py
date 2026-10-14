"""Repository identity protects settings across adoption and replacement."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.adapters.outbound.settings.k8s_config_store import K8sConfigStore
from orchestrator.adapters.outbound.credentials.k8s_credential_store import K8sCredentialStore
from orchestrator.application.services.identity.repository_incarnation import (
    RepositoryIncarnation,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.repository_identity import RepositoryIdentity


class Credentials:
    def __init__(self) -> None:
        self.values = {"app": "secret"}

    def delete_delivery(self, slug: str) -> None:
        self.values.pop(slug, None)


@pytest.mark.parametrize("bound", [False, True])
def test_adopting_same_repository_preserves_settings_and_credentials(bound: bool) -> None:
    identity = RepositoryIdentity("org/app", "100")
    repositories = SimpleNamespace(repository_identity=lambda repo: identity)
    settings = InMemoryConfigStore()
    settings.put_setting("target-app", {"model": "chosen", "timeout_seconds": "600"}, None)
    if bound:
        settings.bind_repository_identity("app", identity)
    credentials = Credentials()
    service = RepositoryIncarnation(repositories, settings, credentials)
    assert service.reconcile("org/app", service.observe("org/app")) == identity
    assert settings.get_setting("target-app")["model"] == "chosen"
    assert credentials.values == {"app": "secret"}
    assert settings.repository_identity("app") == identity


@pytest.mark.parametrize("created", [False, True])
def test_authoritative_new_or_recreated_identity_clears_only_target_state(created: bool) -> None:
    identity = RepositoryIdentity("org/app", "200")
    old = RepositoryIdentity("org/app", "100")
    settings = InMemoryConfigStore()
    settings.bind_repository_identity("app", old)
    settings.put_setting("target-app", {"model": "old"}, None)
    settings.put_setting("run-retention", {"history": "keep"}, None)
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: identity), settings, credentials)
    assert service.reconcile("org/app", None if created else identity) == identity
    assert settings.get_setting("target-app") == {"configured": False}
    assert credentials.values == {}
    assert settings.get_setting("run-retention")["history"] == "keep"
    assert settings.repository_identity("app") == identity


def test_cleanup_failure_preserves_old_binding_and_surfaces_failure() -> None:
    old = RepositoryIdentity("org/app", "100")
    new = RepositoryIdentity("org/app", "200")
    settings = InMemoryConfigStore()
    settings.bind_repository_identity("app", old)
    credentials = Credentials()

    def refused(slug: str) -> None:
        raise SourceUnavailable("cleanup refused")

    credentials.delete_delivery = refused
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: new), settings, credentials)
    with pytest.raises(SourceUnavailable):
        service.reconcile("org/app", old)
    assert settings.repository_identity("app") == old


def test_replacement_during_establish_clears_unbound_old_selection() -> None:
    old = RepositoryIdentity("org/app", "100")
    new = RepositoryIdentity("org/app", "200")
    settings = InMemoryConfigStore()
    settings.put_setting("target-app", {"model": "old"}, None)
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: new), settings, credentials)
    service.reconcile("org/app", old)
    assert credentials.values == {}
    assert settings.get_setting("target-app") == {"configured": False}
    assert settings.repository_identity("app") == new


def test_failed_authoritative_observation_cannot_clear_any_target_state() -> None:
    settings = InMemoryConfigStore()
    settings.put_setting("target-app", {"model": "chosen"}, None)
    credentials = Credentials()

    def unavailable(repo: str) -> RepositoryIdentity | None:
        raise SourceUnavailable("host unavailable")

    service = RepositoryIncarnation(SimpleNamespace(repository_identity=unavailable), settings, credentials)
    with pytest.raises(SourceUnavailable):
        service.observe("org/app")
    assert credentials.values == {"app": "secret"}
    assert settings.get_setting("target-app")["model"] == "chosen"


@pytest.mark.parametrize("bound_id", [None, "100"])
def test_target_credential_use_requires_matching_authoritative_binding(bound_id: str | None) -> None:
    identity = RepositoryIdentity("org/app", "200")
    settings = InMemoryConfigStore()
    if bound_id:
        settings.bind_repository_identity("app", RepositoryIdentity("org/app", bound_id))
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: identity), settings, credentials)
    with pytest.raises(SourceUnavailable):
        service.verify_current("org/app")
    assert credentials.values == {"app": "secret"}


def test_matching_binding_allows_target_credential_use_without_mutation() -> None:
    identity = RepositoryIdentity("org/app", "200")
    settings = InMemoryConfigStore()
    settings.bind_repository_identity("app", identity)
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: identity), settings, credentials)
    assert service.verify_current("org/app") == identity
    assert credentials.values == {"app": "secret"}


def test_identity_store_outage_is_not_an_absent_binding(monkeypatch) -> None:
    monkeypatch.setenv("FC_LIVE", "1")
    monkeypatch.setattr("orchestrator.adapters.outbound.settings.k8s_config_store.subprocess.run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="refused"))
    with pytest.raises(SourceUnavailable):
        K8sConfigStore().repository_identity("app")


def test_credential_cleanup_failure_is_reported(monkeypatch) -> None:
    monkeypatch.setenv("FC_LIVE", "1")
    monkeypatch.setattr("orchestrator.adapters.outbound.credentials.k8s_credential_store.subprocess.run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="refused"))
    with pytest.raises(RuntimeError):
        K8sCredentialStore().delete_delivery("app")


@intent("INT-FC-R171")
def test_first_settings_write_binds_a_maintained_repository_for_later_drives() -> None:
    identity = RepositoryIdentity("org/app", "100")
    settings = InMemoryConfigStore()
    credentials = Credentials()
    credentials.values = {}
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: identity), settings, credentials)
    with pytest.raises(SourceUnavailable):
        service.verify_current("org/app")
    assert service.adopt("org/app") == identity
    assert service.verify_current("org/app") == identity


@intent("INT-FC-R171")
def test_settings_write_keeps_the_bound_incarnation_settings() -> None:
    identity = RepositoryIdentity("org/app", "100")
    settings = InMemoryConfigStore()
    settings.bind_repository_identity("app", identity)
    settings.put_setting("target-app", {"model": "chosen"}, None)
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: identity), settings, credentials)
    service.adopt("org/app")
    assert settings.get_setting("target-app")["model"] == "chosen"
    assert credentials.values == {"app": "secret"}


@intent("INT-FC-R171")
@pytest.mark.parametrize("previous", [None, RepositoryIdentity("org/app", "100")])
def test_settings_write_clears_state_retained_for_another_incarnation(previous) -> None:
    identity = RepositoryIdentity("org/app", "200")
    settings = InMemoryConfigStore()
    if previous is not None:
        settings.bind_repository_identity("app", previous)
    settings.put_setting("target-app", {"model": "predecessor"}, None)
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: identity), settings, credentials)
    assert service.adopt("org/app") == identity
    assert settings.get_setting("target-app") == {"configured": False}
    assert credentials.values == {}
    assert settings.repository_identity("app") == identity


@intent("INT-FC-R171")
def test_settings_write_for_an_unobservable_repository_changes_nothing() -> None:
    settings = InMemoryConfigStore()
    settings.put_setting("target-app", {"model": "kept"}, None)
    credentials = Credentials()
    service = RepositoryIncarnation(SimpleNamespace(repository_identity=lambda repo: None), settings, credentials)
    with pytest.raises(SourceUnavailable):
        service.adopt("org/app")
    assert settings.get_setting("target-app")["model"] == "kept"
    assert credentials.values == {"app": "secret"}


def _maintained_repository(identity):
    from capability_support import UnitCredentials, make_capabilities
    repos = SimpleNamespace(repository_identity=lambda repo: identity, list_delivery_repos=lambda: [])
    settings = InMemoryConfigStore()
    credentials = UnitCredentials()
    incarnations = RepositoryIncarnation(repos, settings, credentials)
    service = make_capabilities(repos, config=settings, credentials=credentials, incarnations=incarnations)
    return service, settings, credentials, incarnations


@intent("INT-FC-R171")
def test_settings_commands_bind_a_maintained_repository_its_drive_then_accepts() -> None:
    from capability_support import command_kwargs
    from orchestrator.application.services.runs.prepare_config import prepare_config
    from orchestrator.domain.model.run_config import RunConfig
    identity = RepositoryIdentity("example-org/acme", "200")
    service, settings, credentials, incarnations = _maintained_repository(identity)
    settings.put_setting("target-acme", {"model": "predecessor", "timeout_seconds": "900"}, None)
    credentials.values["acme"] = "predecessor-token"
    service.set_delivery_model.execute("example-org/acme", "claude", "", "opus", "fresh-token", **command_kwargs("example-org/acme"))
    assert settings.repository_identity("acme") == identity
    assert credentials.values == {"acme": "fresh-token"}
    assert settings.get_setting("target-acme")["model"] == "opus"
    assert "timeout_seconds" not in settings.get_setting("target-acme")
    service.set_delivery_timeout.execute("example-org/acme", 5400, **command_kwargs("example-org/acme"))
    service.set_delivery_model.execute("example-org/acme", "claude", "", "sonnet", None, **command_kwargs("example-org/acme"))
    assert credentials.values == {"acme": "fresh-token"}
    assert settings.get_setting("target-acme")["timeout_seconds"] == "5400"
    config, bound = prepare_config("example-org/acme", RunConfig(None, "example-org/acme", True),
                                   config=settings, credentials=credentials, incarnations=incarnations,
                                   context=command_kwargs("example-org/acme")["context"])
    assert bound == identity
    assert (config.worker_model, config.worker_timeout_seconds) == ("sonnet", 5400)


@intent("INT-FC-R171")
def test_a_settings_command_for_an_unobservable_repository_changes_nothing() -> None:
    from capability_support import command_kwargs
    from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
    service, settings, credentials, _ = _maintained_repository(None)
    settings.put_setting("target-acme", {"model": "kept"}, None)
    credentials.values["acme"] = "kept-token"
    with pytest.raises(OperationUnknown):
        service.set_delivery_model.execute("example-org/acme", "claude", "", "opus", "fresh-token", **command_kwargs("example-org/acme"))
    assert settings.get_setting("target-acme")["model"] == "kept"
    assert credentials.values == {"acme": "kept-token"}
