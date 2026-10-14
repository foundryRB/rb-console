"""The runtime driver config: any Anthropic-compatible endpoint, persisted via a store,
the api_key held (whether it is set is reported, the value never returned)."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from capability_support import make_capabilities

class FakeRepos:

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        return target

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

@intent('INT-FC-R27')
def test_driver_config_round_trips_without_exposing_the_key():
    service = make_capabilities(FakeRepos(), config=InMemoryConfigStore())
    cfg = service.set_driver_config.execute('https://api.deepseek.com', 'deepseek-chat', 'sk-secret', **command_kwargs(''))
    assert cfg.base_url == 'https://api.deepseek.com'
    assert cfg.model == 'deepseek-chat'
    assert cfg.configured is True
    got = service.driver_config.execute()
    assert got.configured is True
    assert 'sk-secret' not in repr(got)

@intent('INT-FC-R28')
def test_updating_fields_keeps_the_existing_key_when_none_is_given():
    service = make_capabilities(FakeRepos(), config=InMemoryConfigStore())
    service.set_driver_config.execute('https://api.openai.com', 'gpt-4o', 'sk-1', **command_kwargs(''))
    cfg = service.set_driver_config.execute('https://api.openai.com', 'gpt-4o-mini', '', **command_kwargs(''))
    assert cfg.model == 'gpt-4o-mini'
    assert cfg.configured is True

@intent('INT-FC-R29')
def test_per_door_mcp_is_a_runtime_setting_that_hides_the_secret():
    service = make_capabilities(FakeRepos(), config=InMemoryConfigStore())
    m = service.set_setting.execute('mcp-playbook-studio', {'user': 'admin'}, 'pw-secret', **command_kwargs(''))
    assert m['user'] == 'admin' and m['configured'] is True and ('pw-secret' not in repr(m))
    assert service.set_setting.execute('mcp-playbook-studio', {'user': 'admin'}, '', **command_kwargs(''))['configured'] is True


@intent('INT-FC-R55')
def test_a_timed_out_turn_names_the_timeout_and_never_its_command_line(monkeypatch):
    """The timeout's own text is the command line, which carries the rendered transcript and
    the grounding; the turn's error must carry neither."""
    import subprocess
    import pytest
    from orchestrator.adapters.outbound.agents.http_driver_agent import HttpDriverAgent

    def expire(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", expire)
    with pytest.raises(RuntimeError) as raised:
        HttpDriverAgent().chat("GROUNDING-SECRET", [{"role": "user", "content": "TRANSCRIPT-SECRET"}],
                               credential="sk-ant-api-x", model="haiku", timeout=7)
    assert str(raised.value) == "Driver timed out after 7s"
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
