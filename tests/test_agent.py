from orchestrator.domain.model.repository_tree_entry import RepositoryTreeEntry
from orchestrator.domain.model.repository_file import RepositoryFile
from delivery_fixtures import record_inputs
"""The delivery co-pilot: it degrades to a not-configured hint until the DELIVERY'S OWN
agent credential exists (an open delivery never borrows the home driver; never fabricates
a reply), and once one does it reasons with the phase context and any referenced files.
The service resolves the credential and passes it to the adapter. Audit: csd-intent ."""
from pytest_intent import intent
from orchestrator.domain.services.delivery_resolution import derive_from_records
from capability_support import make_capabilities

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeSource:

    def __init__(self):
        self.files = {'README.md': 'hello world'}

    def scan(self):
        return []

    def state_of(self, repo):
        return derive_from_records(repo, True, record_inputs({}))

    def read_config(self, repo, *, revision=""):
        return {}

    def present_records(self, repo):
        return []

    def tree(self, repo, *, revision="", scratch_revision=""):
        return [RepositoryTreeEntry('README.md', 'file', 11)]

    def content_revision(self, repo, path=""):
        return "unit-head"

    def file(self, repo, path, *, revision=""):
        content = self.files.get(path, '')
        return RepositoryFile(path, content, len(content))

class FakeConfig:
    """The global driver setting (Settings -> Driver)."""

    def __init__(self, secret=''):
        self._secret = secret

    def get_setting(self, name):
        return {'model': '', 'base_url': '', 'configured': bool(self._secret)}

    def get_secret(self, name):
        return self._secret

class FakeDriver:

    def __init__(self):
        self.last = None

    def chat(self, system, messages, *, credential, model='', base_url='', max_tokens=1024):
        self.last = (system, messages, credential)
        return 'advice: do X'

class FakeCreds:
    """The delivery's own agent credential, persisted by slug (the masthead pick)."""

    def __init__(self, secret=''):
        self._secret = secret

    def has_delivery(self, slug):
        return bool(self._secret)

    def get_delivery(self, slug):
        return self._secret

@intent('INT-FC-R44')
def test_chat_degrades_until_configured_then_uses_context_and_references():
    src = FakeSource()
    svc0 = make_capabilities(FakeRepos(), source=src, config=FakeConfig(secret='home-tok'), driver=FakeDriver())
    assert svc0.chat.execute('r', 'scope', 'hi') == {'reply': None, 'configured': False, 'model': None}
    drv = FakeDriver()
    svc = make_capabilities(FakeRepos(), source=src, config=FakeConfig(secret=''), credentials=FakeCreds('sk-tok'), driver=drv)
    out = svc.chat.execute('r', 'scope', "what's next?", references=['README.md'])
    assert out['configured'] is True and out['reply'] == 'advice: do X'
    system, messages, credential = drv.last
    assert credential == 'sk-tok'
    assert 'README.md' in system and 'hello world' in system
    assert messages[-1] == {'role': 'user', 'content': "what's next?"}
    assert svc.repo_tree.execute('r')[0].path == 'README.md'
    assert svc.repo_file.execute('r', 'README.md').content == 'hello world'
