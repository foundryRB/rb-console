from orchestrator.domain.model.repository_file import RepositoryFile
from delivery_fixtures import record_inputs
"""The two co-pilots stay honest: the home co-pilot degrades to not-configured (never a
fabricated reply), a line-range reference slices exactly the pointed-at lines, and a
turn is never awaited on the wire - it starts in the background and polls to its reply."""
import time
from pytest_intent import intent
from capability_support import make_capabilities

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeConfig:

    def __init__(self, secret=''):
        self._secret = secret

    def get_setting(self, name):
        return {'base_url': 'https://api.example.test', 'model': 'deepseek-chat'}

    def get_secret(self, name):
        return self._secret

class EchoDriver:

    def __init__(self):
        self.seen_system = ''

    def chat(self, system, messages, *, credential, model, base_url):
        self.seen_system = system
        return 'advice'

def test_fleet_chat_degrades_without_a_driver_credential():
    svc = make_capabilities(FakeRepos(), config=FakeConfig(secret=''), driver=EchoDriver())
    out = svc.fleet_chat.execute('where do things stand?')
    assert out == {'reply': None, 'configured': False, 'model': None}

class FakeStudioGateway:

    def health(self):
        from orchestrator.domain.model.studio_health import StudioHealth
        return [StudioHealth('estimatekit', True, 'reachable', None)]

    def platform_apps(self):
        return []

@intent('INT-FC-R54')
def test_fleet_chat_grounds_in_the_floor_and_never_claims_to_execute():
    driver = EchoDriver()
    from orchestrator.adapters.outbound.memory.studios_index import StudioStatusIndex
    observations = StudioStatusIndex()
    observations.refresh(FakeStudioGateway(), [])
    svc = make_capabilities(FakeRepos(), config=FakeConfig(secret='k'), driver=driver, studios=FakeStudioGateway(), studio_index=observations)
    out = svc.fleet_chat.execute('what next?')
    assert out['configured'] is True and out['reply'] == 'advice'
    assert 'You never execute' in driver.seen_system
    assert 'estimatekit: reachable' in driver.seen_system
    assert 'REF-Delivery contract, distilled' in driver.seen_system

class OneDeliveryCred:

    def has_delivery(self, slug):
        return True

    def get_delivery(self, slug):
        return 'k'

class OneFileSource:

    def content_revision(self, repo, path=""):
        return "abc123"

    def scan(self):
        return []

    def state_of(self, repo):
        from orchestrator.domain.services.delivery_resolution import derive_from_records
        return derive_from_records(repo, True, record_inputs({}))

    def read_config(self, repo):
        return {}

    def file(self, repo, path, *, revision=""):
        return RepositoryFile(path, 'L1\nL2\nL3\nL4\nL5', 14)

@intent('INT-FC-R54')
def test_chat_reference_with_a_line_range_slices_those_lines():
    driver = EchoDriver()
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret='k'), credentials=OneDeliveryCred(), driver=driver)
    svc.chat.execute('o/r', 'scope', 'why?', references=['app.py#L2-L4'])
    assert '(lines 2-4)' in driver.seen_system
    assert 'L2\nL3\nL4' in driver.seen_system
    assert 'L1' not in driver.seen_system.split('(lines 2-4) ---')[-1].split('---')[0]
    assert 'REF-Delivery contract, distilled' in driver.seen_system

@intent('INT-FC-R54')
def test_maintenance_turns_carry_the_maintenance_contract_digest():
    """A maintenance-context turn grounds in the REF-Maintenance digest (the loop, the
    three per-act modes, the verdict gate, derived state) plus the derived positions -
    the second contract digest the claim names."""
    driver = EchoDriver()
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret='k'), credentials=OneDeliveryCred(), driver=driver)
    out = svc.chat.execute('o/r', 'maintenance', 'what needs me?')
    assert out['configured'] is True
    assert 'REF-Maintenance contract, distilled' in driver.seen_system
    assert 'gated' in driver.seen_system and 'one-shot' in driver.seen_system
    assert 'VERDICT: PASS' in driver.seen_system and 'VERDICT: FAIL' in driver.seen_system
    assert 'VERDICT: UNRECORDED' in driver.seen_system
    assert 'never execute anything' in driver.seen_system
    assert 'REF-Delivery contract, distilled' not in driver.seen_system

class NoDeliverySource(OneFileSource):

    def state_of(self, repo):
        from orchestrator.domain.services.delivery_resolution import derive_from_records
        return derive_from_records(repo, False, record_inputs({}))

@intent('INT-FC-R44')
def test_chat_voice_is_scoped_delivery_agent_only_home_driver_only_for_projects():
    """An OPEN delivery never silently borrows the home driver: its masthead agent is the
    one voice, or the hint says to pick one. Only a repo with NO open line (the project
    view) answers on the home co-pilot's driver - there is no delivery to carry an agent."""
    driver = EchoDriver()
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret='home'), driver=driver)
    assert svc.chat.execute('o/r', 'scope', 'hi') == {'reply': None, 'configured': False, 'model': None}
    from orchestrator.adapters.outbound.memory.index import DeliveryIndex
    source = NoDeliverySource()
    observations = DeliveryIndex()
    observations.put(source.state_of('o/r'))
    svc = make_capabilities(FakeRepos(), source=source, index=observations, config=FakeConfig(secret='home'), driver=driver)
    assert svc.chat.execute('o/r', '', 'hi')['configured'] is True

def _await_turn(svc, turn_id, timeout=5.0):
    """Poll a started turn to its terminal state (the SPA's loop, compressed)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = svc.chat_poll.execute(turn_id)
        if out['status'] != 'running':
            return out
        time.sleep(0.01)
    raise AssertionError('the turn never finished')

@intent('INT-FC-R55')
def test_a_chat_turn_starts_off_the_wire_and_polls_to_its_reply():
    """The proxy chain severs a synchronous POST at 30s (a bare 502 in the chat):
    start must hand back a turn id at once, and the poll lands the same honest dict."""
    driver = EchoDriver()
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret='k'), credentials=OneDeliveryCred(), driver=driver)
    out = svc.chat_start.execute('o/r', 'scope', 'why two phases?')
    assert set(out) == {'turn'}
    done = _await_turn(svc, out['turn'])
    assert done['status'] == 'done' and done['reply'] == 'advice' and (done['configured'] is True)

@intent('INT-FC-R55')
def test_a_failing_or_lost_turn_degrades_to_a_clear_error_never_a_hang():

    class BoomDriver:

        def chat(self, system, messages, *, credential, model, base_url):
            raise RuntimeError('model down')
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret='k'), credentials=OneDeliveryCred(), driver=BoomDriver())
    done = _await_turn(svc, svc.chat_start.execute('o/r', 'scope', 'hi')['turn'])
    assert done['status'] == 'error' and 'model down' in done['error']
    lost = svc.chat_poll.execute('nope')
    assert lost['status'] == 'error' and 'unknown turn' in lost['error']

@intent('INT-FC-R71')
def test_chat_grounding_carries_the_affordances_contract():
    """The co-pilot must KNOW its own contract - toolless by design, the operator's real
    controls, and the redrive staging convention - or it flails: observed live, an
    ungrounded turn attempted a tool call and narrated the denial back at the operator."""
    driver = EchoDriver()
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret='k'), credentials=OneDeliveryCred(), driver=driver)
    svc.chat.execute('o/r', 'scope', 'what should change?')
    sysprompt = driver.seen_system
    assert 'toolless' in sysprompt
    assert 'never attempt a tool call' in sysprompt
    assert 'Re-drive with feedback' in sysprompt
    assert '`redrive`' in sysprompt
    assert 'executes nothing' in sysprompt

@intent('INT-FC-R71')
def test_the_driver_launches_claude_with_no_tools(monkeypatch):
    """Grounding declares the contract; the adapter ENFORCES it: --tools "" offers the
    model nothing to flail against, so the whole bounded turn spends itself on advice."""
    from orchestrator.adapters.outbound.agents import http_driver_agent as da
    seen = {}

    class Proc:
        returncode = 0
        stdout = '{"result": "advice"}'
        stderr = ''

    def fake_run(argv, **kwargs):
        seen['argv'] = argv
        return Proc()
    monkeypatch.setattr(da.subprocess, 'run', fake_run)
    out = da.HttpDriverAgent().chat('sys', [{'role': 'user', 'content': 'hi'}], credential='tok')
    assert out == 'advice'
    i = seen['argv'].index('--tools')
    assert seen['argv'][i + 1] == ''

def test_base_url_gateways_receive_both_auth_headers(monkeypatch):
    """A compatible gateway may read the credential as x-api-key (OpenCode Zen, the real
    Anthropic convention) or as Authorization: Bearer (DeepSeek, OAuth proxies). The adapter
    can't know which, so base_url mode exports BOTH ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN
    and the gateway ignores the header it does not use. Sending only Bearer 401'd against Zen's
    x-api-key /v1/messages ("Missing API key"), stalling the co-pilot on that endpoint."""
    from orchestrator.adapters.outbound.agents import http_driver_agent as da
    seen = {}

    class Proc:
        returncode = 0
        stdout = '{"result": "ok"}'
        stderr = ''

    def fake_run(argv, **kwargs):
        seen['env'] = kwargs['env']
        return Proc()
    monkeypatch.setattr(da.subprocess, 'run', fake_run)
    da.HttpDriverAgent().chat('sys', [{'role': 'user', 'content': 'hi'}], credential='zen-tok', base_url='https://opencode.ai/zen/go')
    env = seen['env']
    assert env['ANTHROPIC_BASE_URL'] == 'https://opencode.ai/zen/go'
    assert env['ANTHROPIC_API_KEY'] == 'zen-tok'
    assert env['ANTHROPIC_AUTH_TOKEN'] == 'zen-tok'

@intent('INT-FC-R55')
def test_a_not_configured_turn_still_lands_honestly_through_the_poll():
    """The degrade contract survives the async wrapper: the poll serves the same
    not-configured dict the synchronous use case returns (never a fabricated reply)."""
    svc = make_capabilities(FakeRepos(), config=FakeConfig(secret=''), driver=EchoDriver())
    done = _await_turn(svc, svc.fleet_chat_start.execute('where do things stand?')['turn'])
    assert done['status'] == 'done'
    assert done['reply'] is None and done['configured'] is False and (done['model'] is None)


def test_chat_log_grounding_uses_compiled_repository_and_kind_identity():
    import json

    from orchestrator.adapters.outbound.argo.argo_workflow_compiler import ArgoWorkflowCompiler
    from orchestrator.adapters.outbound.argo.argo_workflow_runner import parse_runs
    from orchestrator.domain.model.delivery_state import DeliveryState
    from orchestrator.domain.model.run_config import RunConfig

    rows = []
    for repo, run_id, known in [("other/app", "d-foreign", True), ("owner/app", "d-unknown", False), ("owner/app", "d-owned", True)]:
        state = DeliveryState(repo, True, "run-phase", "scope", None, None, None, (), (), scratch_ref="delivery/current")
        compiled = ArgoWorkflowCompiler().compile_delivery(repo, state, RunConfig("credential", repo, True), run_id=run_id)
        payload = json.loads(compiled.executor_payload)
        if not known:
            payload["metadata"]["annotations"].pop("foundry-console/scratch-ref")
        payload["status"] = {"phase": "Running"}
        rows.extend(parse_runs({"items": [payload]}))

    class Workflows:
        def __init__(self):
            self.requested = []

        def list_runs(self):
            return rows

        def logs(self, handle, tail=50):
            self.requested.append(handle)
            return "owned execution diagnostic"

    workflows = Workflows()
    driver = EchoDriver()
    svc = make_capabilities(FakeRepos(), source=OneFileSource(), config=FakeConfig(secret="k"), credentials=OneDeliveryCred(), driver=driver, workflows=workflows)
    svc.chat.execute("owner/app", "scope", "what happened?")
    assert workflows.requested == ["live:workflow.argoproj.io/d-owned"]
    assert "owned execution diagnostic" in driver.seen_system
    assert "d-foreign" not in driver.seen_system and "d-unknown" not in driver.seen_system
