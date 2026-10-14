"""Which apps are promotion subjects at all.

Two apps declare a contract and still have no promotion positions to derive, and both are
facts about the APP rather than about any target: a Managed app (no entry environment, so
promotion has nothing to move - its repository target is its HOME, not a door), and an app
that has proven no release yet. Left to the per-target derivation, both came out PENDING,
because an empty proven compares unequal to anything - which put a Promote act on a row
where no promotion is possible. The view answers both before any target is looked at.

Audit: csd-intent .
"""
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.application.promotion import NOT_SUBJECT_MANAGED, NOT_SUBJECT_UNPROVEN, promotion_view
from capability_support import make_capabilities
from promotion_support import observe_promotion

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeMaint:

    def __init__(self, tags):
        self._tags = list(tags)

    def tags(self, repo):
        return self._tags
HOME_CONTRACT = 'targets:\n  - name: acme-home\n    kind: repository\n    repo: acme/portal\n    branch: main\n    credential: acme-portal-push\n    door: pull-request\n    terms: source\n    acceptance: none\n'

class FakeSource:

    def __init__(self, installs, contract=HOME_CONTRACT):
        self._installs = installs
        self._contract = contract
        self.reads = 0

    def contract_text(self, repo):
        return self._contract

    def deploy_installs(self, repo):
        return self._installs

    def environment_values(self, repo, install, environment):
        self.reads += 1
        return 'tag: 1.0.0\n'

    def open_door(self, repo, base, credential=''):
        self.reads += 1
        return ''

    def last_merged_release(self, repo, base, credential=''):
        self.reads += 1
        return ''

    def probe(self, url):
        return True

@intent('INT-FC-R134')
def test_a_managed_app_is_not_a_promotion_subject_and_its_home_is_never_read():
    source = FakeSource(installs={})
    view = promotion_view(repo='org/app', proven='', source=source, registered=lambda n: True, has_entry_environment=False)
    assert view['declared'] is True
    assert view['subject'] == NOT_SUBJECT_MANAGED
    assert view['positions'] == [] and view['queue'] == []
    assert source.reads == 0

@intent('INT-FC-R134')
def test_an_app_that_has_proven_nothing_has_nothing_to_promote():
    source = FakeSource(installs={'example': ['prod']})
    view = promotion_view(repo='org/app', proven='', source=source, registered=lambda n: True)
    assert view['subject'] == NOT_SUBJECT_UNPROVEN
    assert view['positions'] == []
    assert source.reads == 0

@intent('INT-FC-R134')
def test_a_subject_derives_rows_as_before():
    source = FakeSource(installs={'example': ['prod']})
    view = promotion_view(repo='org/app', proven='2.1.0', source=source, registered=lambda n: True)
    assert view['subject'] == ''
    assert len(view['positions']) == 1

@intent('INT-FC-R134')
def test_a_contract_with_no_targets_is_a_subject_with_nothing_declared():
    source = FakeSource(installs={'example': ['prod']}, contract='targets: []\n')
    view = promotion_view(repo='org/app', proven='', source=source)
    assert view['subject'] == '' and view['positions'] == []

@intent('INT-FC-R134')
def test_the_service_answers_the_tier_from_the_apps_own_repo():
    managed = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), msource=FakeMaint([]), psource=FakeSource(installs={}))
    observe_promotion(managed, 'org/app')
    assert managed.promotion_state.execute('org/app')['subject'] == NOT_SUBJECT_MANAGED
    unproven = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), msource=FakeMaint([]), psource=FakeSource(installs={'example': ['prod']}))
    observe_promotion(unproven, 'org/app')
    assert unproven.promotion_state.execute('org/app')['subject'] == NOT_SUBJECT_UNPROVEN
    hybrid = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), msource=FakeMaint(['v2.1.0']), psource=FakeSource(installs={'example': ['prod']}))
    observe_promotion(hybrid, 'org/app')
    state = hybrid.promotion_state.execute('org/app')
    assert state['subject'] == '' and len(state['targets']) == 1
