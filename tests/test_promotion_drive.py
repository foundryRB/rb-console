"""Driving a promotion: the act the console could name and never perform (issue #131).

Two halves, and the refusals matter more than the happy path. The compiler must carry the
pair's grant to the pod as a REF and the pair's repository as a plain fact (the entrypoint
scopes the credential helper to it), and the drive must refuse - before any pod exists -
every promotion that cannot be performed, including the one that is doctrine rather than
mechanics: promotion never reaches a Managed app.

Audit: csd-intent .
"""
from capability_support import command_kwargs
import pytest
import json
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.domain.services.delivery_launch import HEADLESS_TURN
from orchestrator.domain.services.promotion_launch import PROMOTE_AGENT, PROMOTE_PHASE, PromotionRefused
from orchestrator.adapters.outbound.argo.promotion_launch import compile_promotion_workflow
from capability_support import make_capabilities
from orchestrator.domain.model.git_identity import GitIdentity
from orchestrator.domain.model.pair_credential import PairCredential
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.model.run_config import RunConfig

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeMaintenance:

    def __init__(self, tags=('v2.1.0',)):
        self._tags = list(tags)

    def tags(self, repo):
        return self._tags
PAIR_CONTRACT = 'targets:\n  - name: acme-portal\n    kind: repository\n    repo: acme/portal\n    branch: main\n    credential: acme-portal-push\n    door: pull-request\n    terms: source\n    acceptance: none\n'
ENV_CONTRACT = 'targets:\n  - name: example-prod\n    kind: environment\n    install: example\n    environment: prod\n    door: commit\n    terms: version\n    acceptance: none\n'

class FakeSource:

    def __init__(self, contract=PAIR_CONTRACT, installs=None):
        self._contract = contract
        self._installs = {'example': ['prod', 'staging']} if installs is None else installs

    def repository_revision(self, repo):
        return "a" * 40

    def contract_text(self, repo, *, revision=""):
        assert revision == "a" * 40
        return self._contract

    def deploy_installs(self, repo):
        return self._installs

    def environment_values(self, repo, install, environment):
        return 'tag: 2.1.0\n'

    def open_door(self, repo, base, credential=''):
        return ''

    def last_merged_release(self, repo, base, credential=''):
        return ''

    def probe(self, url):
        return True

class FakeCredentials:
    """A project with an agent already seated: the promotion drive folds the persisted
    credential exactly as a delivery or maintenance drive does, so only the REF travels."""

    def has_delivery(self, slug):
        return True

    def delivery_ref(self, slug):
        return f'fc-delivery-{slug}'

    def put(self, run_id, credential):
        return f'fc-run-{run_id}'

class FakeWorkflows:

    def __init__(self):
        self.submitted = []

    def submit(self, workflow):
        self.submitted.append(workflow)
        return 'wf-1'

def _svc(source=None, workflows=None, tags=('v2.1.0',)):
    """A console with an agent already seated for the project, so these tests exercise the
    PROMOTION refusals rather than the worker-credential precondition every drive shares."""
    return make_capabilities(FakeRepos(), workflows=workflows or FakeWorkflows(), credentials=FakeCredentials(), config=InMemoryConfigStore(), msource=FakeMaintenance(tags), psource=source or FakeSource())
PAIR_TARGET = PromotionTarget(name='acme-portal', kind=TargetKind.REPOSITORY, door='pull-request', terms='source', acceptance='none', repo='acme/portal', branch='main', credential='acme-portal-push')
ENV_TARGET = PromotionTarget(name='example-prod', kind=TargetKind.ENVIRONMENT, door='commit', terms='version', acceptance='none', install='example', environment='prod')

def _env(workflow, step='worker-promote'):
    if isinstance(workflow, CompiledWorkflow):
        workflow = json.loads(workflow.executor_payload)
    for t in workflow['spec']['templates']:
        if t['name'] == step:
            return {e['name']: e for e in t['container']['env']}
    raise AssertionError(f'no {step} step in the workflow')

@intent('INT-FC-R128')
def test_a_pair_door_carries_the_grant_by_ref_and_the_pair_repo_as_a_fact():
    wf = compile_promotion_workflow('org/app', PAIR_TARGET, '2.1.0', RunConfig('tok', 'org/app', True), run_id='p1', pair=PairCredential(secret_name='fc-pair-acme-portal-push-key', host_cm='fc-pair-acme-portal-push'), git_identity=GitIdentity(user_cm='fc-gitid-foundry-delivery', secret_name='fc-gitid-foundry-delivery-key'))
    env = _env(wf)
    assert env['FC_PAIR_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-pair-acme-portal-push-key'
    assert 'value' not in env['FC_PAIR_TOKEN']
    assert env['FC_PAIR_HOST']['valueFrom']['configMapKeyRef']['name'] == 'fc-pair-acme-portal-push'
    assert env['FC_PAIR_REPO']['value'] == 'acme/portal'
    assert env['FC_PROMOTE_TARGET']['value'] == 'acme-portal'
    assert env['FC_RELEASE']['value'] == '2.1.0'
    assert env['FC_GIT_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-gitid-foundry-delivery-key'
    assert env['FC_PHASE']['value'] == PROMOTE_PHASE
    assert len(wf['spec']['templates'][0]['steps']) == 1

@intent('INT-FC-R128')
def test_an_environment_door_carries_no_pair_anything():
    wf = compile_promotion_workflow('org/app', ENV_TARGET, '2.1.0', RunConfig('tok', 'org/app', True), run_id='p2')
    env = _env(wf)
    assert 'FC_PAIR_TOKEN' not in env
    assert 'FC_PAIR_HOST' not in env
    assert env['FC_PAIR_REPO']['value'] == ''
    assert env['FC_PROMOTE_TARGET']['value'] == 'example-prod'

@intent('INT-FC-R128')
def test_a_repository_door_without_a_resolved_pair_is_a_mis_compile():
    with pytest.raises(PromotionRefused):
        compile_promotion_workflow('org/app', PAIR_TARGET, '2.1.0', RunConfig('tok', 'org/app', True), run_id='p3')

@intent('INT-FC-R158')
def test_the_promote_prompt_forbids_parking_on_a_background_job():
    pair = PairCredential(secret_name='fc-pair-acme-portal-push-key', host_cm='fc-pair-acme-portal-push')
    for target, grant in ((ENV_TARGET, None), (PAIR_TARGET, pair)):
        wf = compile_promotion_workflow('org/app', target, '2.1.0', RunConfig('tok', 'org/app', True), run_id='p4', pair=grant)
        step = next((t for t in wf['spec']['templates'] if t['name'] == 'worker-promote'))
        low = step['container']['args'][0].lower()
        assert HEADLESS_TURN.lower() in low
        assert 'must actually exist when you stop' in low

@intent('INT-FC-R129')
def test_promotion_never_reaches_a_managed_app():
    """An app onboarded to no install has no entry environment, so nothing can prove a release
    live: it is Managed, its bar is proven-in-CI-and-merged, and its changes cross back through
    the delivery or maintenance line. A build that lets a promotion reach it has broken the
    model rather than completed it (#130)."""
    svc = _svc(FakeSource(installs={}))
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    with pytest.raises(ValueError) as exc:
        svc.promotion_drive.execute('org/app', 'acme-portal', **command_kwargs('org/app'))
    assert 'Managed' in str(exc.value)

@intent('INT-FC-R129')
def test_a_shut_door_refuses_the_drive_where_the_operator_is():
    svc = _svc()
    with pytest.raises(ValueError) as exc:
        svc.promotion_drive.execute('org/app', 'acme-portal', **command_kwargs('org/app'))
    assert 'acme-portal-push' in str(exc.value)

@intent('INT-FC-R129')
def test_an_undeclared_target_is_refused_and_lists_what_is_declared():
    svc = _svc()
    with pytest.raises(ValueError) as exc:
        svc.promotion_drive.execute('org/app', 'not-a-target', **command_kwargs('org/app'))
    assert 'acme-portal' in str(exc.value)

@intent('INT-FC-R129')
def test_no_published_release_is_refused():
    svc = _svc(tags=())
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    with pytest.raises(ValueError) as exc:
        svc.promotion_drive.execute('org/app', 'acme-portal', **command_kwargs('org/app'))
    assert 'release' in str(exc.value)

@intent('INT-FC-R129')
def test_a_held_credential_drives_the_door_and_the_run_names_what_it_carries():
    workflows = FakeWorkflows()
    svc = _svc(workflows=workflows)
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    svc.set_git_roles.execute({PROMOTE_AGENT: 'Foundry Delivery'}, **command_kwargs(''))
    authority = command_kwargs('org/app')
    receipt = svc.promotion_drive.execute('org/app', 'acme-portal', **authority)
    replayed = svc.promotion_drive.execute('org/app', 'acme-portal', **authority)
    assert replayed == receipt and type(replayed) is type(receipt)
    assert len(workflows.submitted) == 1
    assert receipt.target == 'acme-portal'
    assert receipt.release == '2.1.0'
    assert receipt.handle == 'wf-1'
    env = _env(workflows.submitted[0])
    assert env['FC_PAIR_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-pair-acme-portal-push-key'
    assert env['FC_PAIR_REPO']['value'] == 'acme/portal'
    assert env['FC_GIT_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-gitid-foundry-delivery-key'
    assert 'pat-PAIR' not in str(workflows.submitted[0])

@intent('INT-FC-R129')
def test_the_promotion_role_is_assignable_like_every_other_phase():
    svc = _svc()
    keys = {r['key'] for r in svc.git_role_catalog.execute()}
    assert PROMOTE_AGENT in keys
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', 'their-bot', 'pat-PAIR', **command_kwargs(''))
    assert 'acme-portal-push' not in {i.get('name') for i in svc.list_git_identities.execute()}

def test_the_drive_refusals_reach_the_operator_as_422():
    from fastapi.testclient import TestClient
    from orchestrator.adapters.inbound.http.app import create_app
    svc = _svc(FakeSource(installs={}))
    client = TestClient(create_app(svc))
    r = client.post('/api/promotion/drive', json={'repo': 'org/app', 'target': 'acme-portal'})
    assert r.status_code == 422 and 'Managed' in r.json()['detail']
