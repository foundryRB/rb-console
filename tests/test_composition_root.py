"""The composition root actually wires what the ports promise.

Every other suite hands the service a fake. That is right - the core should never know an
adapter - but it leaves one hole nothing else can cover: whether `container.build_service`
passes the real adapters at all. The hole is dangerous specifically because the ports
DEGRADE by design. A service built without a door reads every pair as unreadable, which is
the correct answer for a console that holds no credential and an indistinguishable one for
a console whose wiring was dropped: no exception, no red, no failing unit test, and every
Managed ticket silently awaiting a PR nobody can see.

So this suite asserts the wiring, not the behaviour: a door is present, and the selector
behind it resolves through the service's own registry. What implementation sits behind
which host is `test_door.py`'s business, and adding the next one must not touch this file.
"""
from __future__ import annotations
from pathlib import Path
from capability_support import command_kwargs
import pytest
from pytest_intent import intent
from orchestrator import container
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore

@pytest.fixture
def service(monkeypatch):
    """The real composition root, with the install's two required values supplied and the
    config store swapped for an in-memory one so nothing reaches a cluster."""
    monkeypatch.setenv('FC_ORG', 'Test-Org')
    monkeypatch.setenv('FC_WORKER_IMAGE', 'ghcr.io/test-org/worker:1.0.0')
    monkeypatch.setattr(container, 'K8sConfigStore', InMemoryConfigStore)
    return container.build_service()

def test_the_console_is_built_with_a_door(service) -> None:
    assert service.maintenance_positions.door is not None

def test_the_door_resolves_its_host_through_the_registry(service) -> None:
    """The selection chain, end to end through the real wiring: the contract names a
    credential, the registration names the host, the host names the implementation."""
    service.set_pair_credential.execute('partner-pair', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    assert service.pair_credential_host.execute('partner-pair') == 'github.com'
    assert service.maintenance_positions.door._host_provider('partner-pair') == 'github.com'
    service.set_pair_credential.execute('partner-pair', 'dev.azure.com', '', None, **command_kwargs(''))
    assert service.maintenance_positions.door._host_provider('partner-pair') == 'dev.azure.com'

def test_a_host_this_foundry_has_no_door_for_degrades_rather_than_raising(service) -> None:
    service.set_pair_credential.execute('elsewhere-pair', 'dev.azure.com', '', 'pat-X', **command_kwargs(''))
    assert service.maintenance_positions.door.pull_request('their/repo', 1, 'elsewhere-pair') is None
    assert service.maintenance_positions.door.open_pull_requests('their/repo', 'main', 'elsewhere-pair') is None

def test_the_install_values_have_no_defaults(monkeypatch) -> None:
    """A default equal to one install's value would run a misconfigured console against the
    wrong org's issues and PRs rather than refusing to start (REF-AppContract section 1)."""
    monkeypatch.delenv('FC_ORG', raising=False)
    monkeypatch.setenv('FC_WORKER_IMAGE', 'ghcr.io/test-org/worker:1.0.0')
    monkeypatch.setattr(container, 'K8sConfigStore', InMemoryConfigStore)
    with pytest.raises(RuntimeError, match='FC_ORG'):
        container.build_service()

@intent('INT-FC-R143')
def test_the_console_token_is_held_and_the_service_can_drop_the_hold(service) -> None:
    """The other invisible-if-dropped wiring, and the reason this file exists. A console
    built WITHOUT the hold behaves identically - every read still resolves a correct token
    - it just re-walks the config store on every GitHub request, which is only visible as
    latency and as the occasional flaky read that reports a configured console as
    unconfigured. No unit test downstream of here would notice."""
    resolves = []
    held = service.set_git_identity.console_credential
    assert held is not None, 'the composition root must hold the console token, not re-resolve it'
    held._resolve = lambda: (resolves.append(1), 'ghp_held')[1]
    held.invalidate()
    for _ in range(50):
        assert held.get() == 'ghp_held'
    assert len(resolves) == 1, 'the hold must survive across reads, not re-resolve per call'
    service.set_git_roles.execute({'console': 'console-bot'}, **command_kwargs(''))
    assert held.get() == 'ghp_held'
    assert len(resolves) == 2


@intent('INT-FC-R170')
def test_assembly_refuses_a_capability_that_misses_its_port(service) -> None:
    from dataclasses import replace
    assert container._verified(service) is service
    with pytest.raises(TypeError, match='PlanNextPort'):
        container._verified(replace(service, plan_next=object()))


@intent('INT-FC-R170')
def test_commands_plan_with_the_committed_delivery_mode_not_the_observed_one(tmp_path) -> None:
    """The observed projection still says interactive before its first observation;
    planning a launch reads the line's committed configuration."""
    import json
    from capability_support import command_kwargs, make_capabilities
    from test_service import GOOD, FakeRepos
    service = make_capabilities(FakeRepos(tmp_path))
    started = service.start.execute('acme', GOOD, **command_kwargs('acme'))
    config = Path(started.state.repo) / '.delivery' / 'config.json'
    config.write_text(json.dumps({**json.loads(config.read_text(encoding='utf-8')), 'mode': 'one-shot'}), encoding='utf-8')
    assert service.delivery_config.execute(started.state.repo)['mode'] == 'interactive'
    action = service.plan_next.execute(started.state.repo, GOOD)
    assert 'This is a one-shot run' in action.launch.prompt


@intent('INT-FC-R170')
def test_every_command_shares_the_current_delivery_configuration(service) -> None:
    current = service.plan_next.cap_delivery_config
    assert current is not service.delivery_config
    for command in (service.advance, service.set_delivery_config, service.set_delivery_model,
                    service.set_delivery_timeout, service.apply_agent_to_delivery,
                    service.reconcile_maintenance_runs):
        assert command.cap_delivery_config is current
    assert service.refresh.cap_refresh_metadata.config is current
    for query in (service.delivery_overview, service.chat):
        assert query.cap_delivery_config is service.delivery_config
