"""Unit tests for the establish path: create-or-adopt (GitHubRepoStore.ensure), where a
repo name freed by renaming the old repo away must be created fresh rather than read as
"already exists" off GitHub's stale rename redirect (bug #29); and register, where the
scratch this console writes has to be the bytes the playbook's helper defines."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
import base64
import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
_VENDORED = Path(__file__).resolve().parents[1] / 'devops' / 'vendor' / 'establish_scratch.py'

def _helper():
    """The vendored scratch helper, loaded the way the adapter loads it."""
    spec = importlib.util.spec_from_file_location('t_establish', _VENDORED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def _use_vendored_establish(monkeypatch):
    """The image bakes the helper at /opt/foundry; a test run has the vendored copy."""
    monkeypatch.setattr('orchestrator.adapters.outbound.github.github_repo_store._ESTABLISH_HELPER', str(_VENDORED))

class _Resp:
    headers = {}
    status = 200

    def __init__(self, body):
        self._body = body

    def read(self, *_size):
        return json.dumps(self._body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

def _wire(monkeypatch, on_get):
    """Route urlopen through ``on_get(path) -> body`` for reads and record every write.
    A read that raises models a 404; the returned body models a 200 (whatever GitHub,
    redirect-followed or not, hands back)."""
    sent = []

    def urlopen(req, timeout=0):
        method, path = (req.get_method(), req.full_url.replace('https://api.github.com', ''))
        if method == 'GET':
            body = on_get(path)
            if isinstance(body, Exception):
                raise body
            return _Resp(body)
        sent.append((method, path))
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout=timeout))
    return sent

@intent('INT-FC-R37')
def test_establish_creates_fresh_over_a_stale_rename_redirect(monkeypatch):

    def on_get(path):
        if path == '/repos/org/alexandria':
            return {'full_name': 'org/alexandria-old', 'name': 'alexandria-old'}
        raise urllib.error.HTTPError('https://api.github.com' + path, 404, 'Not Found', {}, None)
    sent = _wire(monkeypatch, on_get)
    full = GitHubRepoStore('org', lambda: 'tok').ensure('alexandria')
    assert full == 'org/alexandria'
    assert ('POST', '/orgs/org/repos') in sent

@intent('INT-FC-R37')
def test_establish_adopts_a_repo_that_exists_under_the_exact_name(monkeypatch):

    def on_get(path):
        if path == '/repos/org/acme':
            return {'full_name': 'org/acme', 'name': 'acme'}
        raise urllib.error.HTTPError('https://api.github.com' + path, 404, 'Not Found', {}, None)
    sent = _wire(monkeypatch, on_get)
    GitHubRepoStore('org', lambda: 'tok').ensure('acme')
    assert ('POST', '/orgs/org/repos') not in sent

@intent('INT-FC-R37')
def test_repo_exists_answers_the_same_read_ensure_branches_on(monkeypatch):
    """The create-vs-adopt fact, offered before ensure() acts on it (#67). It shares
    ensure()'s definition of taken, so the stale-rename redirect that must not read as
    "already exists" there must not read as "it is there" here either (bug #29)."""

    def on_get(path):
        if path == '/repos/org/SolveOS':
            return {'full_name': 'org/SolveOS', 'name': 'SolveOS'}
        if path == '/repos/org/alexandria':
            return {'full_name': 'org/alexandria-old', 'name': 'alexandria-old'}
        raise urllib.error.HTTPError('https://api.github.com' + path, 404, 'Not Found', {}, None)
    _wire(monkeypatch, on_get)
    store = GitHubRepoStore('org', lambda: 'tok')
    assert store.repo_exists('SolveOS') is True
    assert store.repo_exists('org/SolveOS') is True
    assert store.repo_exists('alexandria') is False
    assert store.repo_exists('MyNewApp') is False

class _Repos:
    """A store holding the repos named in ``holding``; anything else is a greenfield."""

    def __init__(self, holding=()):
        self.ensured = []
        self.asked = []
        self._holding = set(holding)

    def list_delivery_repos(self):
        return []

    def repo_exists(self, target):
        self.asked.append(target)
        return target.split('/')[-1] in self._holding

    def ensure(self, target):
        self.ensured.append(target)
        return f'org/{target}'

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class _SilentRepos:
    """A store that cannot answer the create-vs-adopt read: it offers no repo_exists
    at all, which is what a store predating it looks like. "I cannot tell"."""

    def __init__(self):
        self.ensured = []

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        self.ensured.append(target)
        return f'org/{target}'

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class _Studios:
    """A platform-studio that can be made to answer each way establish branches on."""

    def __init__(self, raises=None):
        self.raises = raises
        self.calls = []
        self.repos_asked = []

    def create_app_repo(self, name, display_name, description, repo=''):
        self.calls.append((name, display_name, description))
        self.repos_asked.append(repo)
        if self.raises is not None:
            raise self.raises
        return {'repo_url': f'https://github.com/org/{name}'}

@intent('INT-FC-R116')
def test_establish_scaffolds_greenfield_via_the_studio():
    """The delivery button asks platform-studio for the templated repo first
    (born carrying the app contract), then ensure adopts it."""
    from capability_support import make_capabilities
    studios, repos = (_Studios(), _Repos())
    service = make_capabilities(repos, studios=studios)
    service.establish.execute('acme-shop', 'Build a store for Acme\nMore detail.', **command_kwargs('acme-shop'))
    assert studios.calls == [('acme-shop', 'Acme Shop', 'Build a store for Acme')]
    assert repos.ensured == ['acme-shop']

@intent('INT-FC-R116')
def test_establish_names_the_app_and_its_repository_apart():
    """The app's fleet name and the repository it ships from are two facts.

    This once passed the repo slug as both, so an organisation that prefixes its
    repositories (a shared org, one prefix per fleet) got a greenfield born with
    that prefix in its namespace, its hostname, its chart and its GHCR packages -
    and the delivery then spent most of a phase renaming the identity back off it
    through an ADR. The scaffold is still rendered for the APP; only the
    repository it lands in is the repo.
    """
    from capability_support import make_capabilities
    studios, repos = (_Studios(), _Repos())
    service = make_capabilities(repos, studios=studios)
    service.establish.execute('team-acme-shop', 'Build a store for Acme', app_name='acme-shop', **command_kwargs('team-acme-shop'))
    assert studios.calls == [('acme-shop', 'Acme Shop', 'Build a store for Acme')]
    assert studios.repos_asked == ['team-acme-shop']
    assert repos.ensured == ['team-acme-shop']

@intent('INT-FC-R116')
def test_establish_defaults_the_app_name_to_the_repository():
    """Unset, the app takes the repository's name - correct wherever an
    organisation names its repositories for the apps they hold, and the behaviour
    every install that names no app keeps unchanged."""
    from capability_support import make_capabilities
    studios, repos = (_Studios(), _Repos())
    service = make_capabilities(repos, studios=studios)
    service.establish.execute('acme-shop', 'Build a store for Acme', **command_kwargs('acme-shop'))
    assert studios.calls == [('acme-shop', 'Acme Shop', 'Build a store for Acme')]
    assert studios.repos_asked == ['acme-shop']

@intent('INT-FC-R116')
def test_establish_degrades_to_bare_when_the_studio_cannot_help():
    """The platform is opt-in: a studio that is down, or up but holding no write
    credential, must not block a delivery from being established."""
    from capability_support import make_capabilities
    from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
    unreachable = OSError('connection refused')
    no_credential = StudioToolError('platform-studio', 'create_app_repo', 'SyncFailedError: repo creation needs the fleet write credential')
    for refusal in (no_credential,):
        studios, repos = (_Studios(raises=refusal), _Repos())
        make_capabilities(repos, studios=studios).establish.execute('acme-shop', **command_kwargs('acme-shop'))
        assert studios.calls
        assert repos.ensured == ['acme-shop']
    from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
    with pytest.raises(OperationUnknown):
        make_capabilities(_Repos(), studios=_Studios(raises=unreachable)).establish.execute('acme-shop', **command_kwargs('acme-shop'))
    repos = _Repos()
    make_capabilities(repos).establish.execute('acme-shop', **command_kwargs('acme-shop'))
    assert repos.ensured == ['acme-shop']

@intent('INT-FC-R116')
def test_establish_adopts_a_repository_that_already_exists():
    from capability_support import make_capabilities
    from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
    studios = _Studios(raises=StudioToolError('platform-studio', 'create_app_repo', 'AlreadyExistsError: repository acme-shop'))
    repos = _Repos()
    make_capabilities(repos, studios=studios).establish.execute('acme-shop', **command_kwargs('acme-shop'))
    assert repos.ensured == ['acme-shop']

@intent('INT-FC-R116')
def test_establish_refuses_when_the_scaffold_failed_halfway():
    """The regression this whole path exists for. A repo whose scaffold could not
    land looks exactly like a healthy new one, so carrying on defers the discovery
    to build-and-ship. establish raises instead, and the endpoint returns 422."""
    import pytest
    from capability_support import make_capabilities
    from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
    studios = _Studios(raises=StudioToolError('platform-studio', 'create_app_repo', 'PrFailedError: could not seed org/acme-shop; the repository was removed again'))
    repos = _Repos()
    from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
    with pytest.raises(OperationUnknown):
        make_capabilities(repos, studios=studios).establish.execute('acme-shop', **command_kwargs('acme-shop'))
    assert repos.ensured == []

def _name_refusals(name):
    """The studio's name refusal at both doors: the typed class name, and the bare
    message a studio predating _typed_refusal sends."""
    from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
    detail = f"invalid app name '{name}': must be a lowercase DNS label (letters, digits, hyphens; starts and ends alphanumeric)"
    return (StudioToolError('platform-studio', 'create_app_repo', detail, 'InvalidAppNameError'),)

@intent('INT-FC-R116')
def test_establish_degrades_to_bare_on_a_name_the_studio_cannot_template():
    """A repo that already exists under a mixed-case name (SolveOS) is one
    establish never got to name: create_app_repo's single `name` is the studio's
    DNS-label app name as well as the repo name, so it refuses - and read as a
    scaffold that failed halfway that 422 blocked the delivery entirely (#67).
    The name is not the operator's to fix from the console; establish falls back
    to the bare create-or-adopt, the same as any other studio that cannot help."""
    from capability_support import make_capabilities
    for refusal in _name_refusals('SolveOS'):
        studios, repos = (_Studios(raises=refusal), _Repos(holding=['SolveOS']))
        make_capabilities(repos, studios=studios).establish.execute('SolveOS', **command_kwargs('SolveOS'))
        assert not studios.calls
        assert repos.asked == ['SolveOS']
        assert repos.ensured == ['SolveOS']

@intent('INT-FC-R116')
def test_establish_still_refuses_a_bad_name_for_a_repo_that_is_not_there():
    """The other half of #67, and the reason the degrade above has to ask the store.
    The studio validates the string and never reaches the repo host, so the refusal
    is IDENTICAL for a repo that exists and for a greenfield the caller just mistyped
    - only the store can tell them apart. Over a name nobody has taken, the caller
    DID choose it: refuse, so the console returns a 422 naming the DNS-label rule and
    one retype fixes it. Swallowing this would create MyNewApp bare - no app
    contract, no templated CI, no deploy branch - and report success."""
    from capability_support import make_capabilities
    for refusal in _name_refusals('MyNewApp'):
        studios, repos = (_Studios(raises=refusal), _Repos())
        with pytest.raises(ValueError, match='DNS label'):
            make_capabilities(repos, studios=studios).establish.execute('MyNewApp', **command_kwargs('MyNewApp'))
        assert repos.ensured == []
    for refusal in _name_refusals('SolveOS'):
        studios, repos = (_Studios(raises=refusal), _SilentRepos())
        with pytest.raises(ValueError, match='DNS label'):
            make_capabilities(repos, studios=studios).establish.execute('SolveOS', **command_kwargs('SolveOS'))
        assert repos.ensured == []

def _wire_register(monkeypatch, refs, present, gitignore='.delivery/\n', empty_repo=False):
    """Route urlopen for the register path: ``refs`` is the repo's delivery/* namespace
    (short branch names), ``present`` the scratch paths that already exist on the ref,
    ``gitignore`` the default branch's .gitignore content (None = the file is absent;
    the default already carries the mount-point line, so tests about other behaviour
    see no ignore write). Records every write as (method, path, body). ``empty_repo``
    makes the git-data trees POST answer 409, the way GitHub does on a repository with
    no commits at all."""
    written = []

    def urlopen(req, timeout=0):
        method = req.get_method()
        path = req.full_url.replace('https://api.github.com', '')
        if method == 'GET':
            if path.endswith('/git/matching-refs/heads/delivery/'):
                return _Resp([{'ref': f'refs/heads/{r}', 'object': {'sha': f'tip-{r}'}} for r in refs])
            rel = path.split('/contents/', 1)[1].partition('?')[0] if '/contents/' in path else ''
            if rel == '.gitignore':
                if gitignore is None:
                    raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
                return _Resp({'content': base64.b64encode(gitignore.encode()).decode(), 'sha': 'sha-ignore'})
            if rel in present:
                return _Resp({'content': '', 'sha': f'sha-{rel}'})
            raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
        body = json.loads(req.data.decode())
        if empty_repo and path.endswith('/git/trees'):
            raise urllib.error.HTTPError(req.full_url, 409, 'Conflict', {}, None)
        written.append((method, path, body))
        if path.endswith('/git/trees'):
            return _Resp({'sha': 'tree0'})
        if path.endswith('/git/commits'):
            return _Resp({'sha': 'commit0'})
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout=timeout))
    return written

@intent('INT-FC-R112')
def test_register_mints_the_orphan_ref_carrying_the_helpers_bytes(monkeypatch, _use_vendored_establish):
    """Register makes the repo a delivery by minting its one orphan delivery/<line-id>
    scratch ref through the git-data API: a fresh root tree carrying the skeleton (and
    the captured request) at the BRANCH ROOT, a parentless commit, then the ref. The
    bytes still have to be the playbook helper's own: a skeleton written from a constant
    here is a second definition that drifts the moment the playbook's moves
    (REF-Delivery anti-pattern 30)."""
    written = _wire_register(monkeypatch, refs=[], present=[])
    GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'Build me a thing.')
    helper = _helper()
    trees = [b for m, p, b in written if p.endswith('/git/trees')]
    commits = [b for m, p, b in written if p.endswith('/git/commits')]
    refs = [b for m, p, b in written if p.endswith('/git/refs')]
    assert len(trees) == len(commits) == len(refs) == 1
    by_path = {e['path']: e.get('content') for e in trees[0]['tree']}
    assert by_path['README.md'] == helper.SKELETON
    assert by_path['request.md'] == helper.request_doc('Build me a thing.')
    assert 'Build me a thing.' in by_path['request.md']
    assert commits[0]['parents'] == []
    assert refs[0]['ref'].startswith('refs/heads/delivery/')
    assert refs[0]['sha'] == 'commit0'

@intent('INT-FC-R112')
def test_register_is_idempotent_so_adopting_a_delivery_keeps_the_ask_it_opened_with(monkeypatch, _use_vendored_establish):
    """A live delivery/* ref is adopted, never doubled: no second mint (the singleton
    guard), and an already-captured request survives a different ask verbatim."""
    written = _wire_register(monkeypatch, refs=['delivery/2026-08-01'], present=['request.md'])
    GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'a DIFFERENT ask')
    assert written == []

@intent('INT-FC-R112')
def test_register_captures_a_missing_request_onto_the_adopted_ref(monkeypatch, _use_vendored_establish):
    """Adopting a line that never captured its ask writes request.md once - onto the
    line's own ref (branch: named, branch-root path), not the default branch."""
    written = _wire_register(monkeypatch, refs=['delivery/2026-08-01'], present=[])
    GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'Build me a thing.')
    assert len(written) == 1
    method, path, body = written[0]
    assert method == 'PUT' and path.endswith('/contents/request.md')
    assert body['branch'] == 'delivery/2026-08-01'
    assert base64.b64decode(body['content']).decode() == _helper().request_doc('Build me a thing.')

@intent('INT-FC-R37')
def test_register_refuses_an_anomalous_ref_namespace(monkeypatch, _use_vendored_establish):
    """Two delivery/* refs is the anomaly every writer refuses on: register neither
    mints a third nor silently picks one to adopt."""
    written = _wire_register(monkeypatch, refs=['delivery/2026-08-01', 'delivery/2026-08-18'], present=[])
    with pytest.raises(RuntimeError, match='exactly one'):
        GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'an ask')
    assert written == []

@intent('INT-FC-R37')
def test_register_ensures_the_default_branch_ignores_the_mount_point(monkeypatch, _use_vendored_establish):
    """An unignored mount point is a gitlink trap: a whole-tree `git add` on the default
    branch stages .delivery as a gitlink, and once that gitlink is committed every later
    worker's `git worktree add .delivery` fails, terminally parking the line. Register
    therefore ensures the .gitignore line on the default branch - creating the file when
    absent, appending (sha carried) when present without the line - and leaves a file
    already carrying it untouched (the adopted-repo case pays one read)."""
    from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
    store = GitHubRepoStore('org', lambda: 'tok', transport=GitHubTransport(opener=lambda request, timeout: urllib.request.build_opener().open(request, timeout=timeout)))

    def ignore_writes(written):
        return [(m, p, b) for m, p, b in written if p.endswith('/contents/.gitignore')]
    written = _wire_register(monkeypatch, refs=['delivery/2026-08-01'], present=['request.md'], gitignore=None)
    store.register('org/acme', 'an ask')
    (method, _, body), = ignore_writes(written)
    assert method == 'PUT'
    assert body['message'] == 'delivery: ignore the scratch mount point'
    assert 'branch' not in body and 'sha' not in body
    assert '.delivery/' in base64.b64decode(body['content']).decode()
    written = _wire_register(monkeypatch, refs=['delivery/2026-08-01'], present=['request.md'], gitignore='node_modules/\n')
    store.register('org/acme', 'an ask')
    (_, _, body), = ignore_writes(written)
    assert body['sha'] == 'sha-ignore'
    text = base64.b64decode(body['content']).decode()
    assert 'node_modules/' in text and '.delivery/' in text
    for existing in ('.delivery/\n', '# app\ndist/\n.delivery\n'):
        written = _wire_register(monkeypatch, refs=['delivery/2026-08-01'], present=['request.md'], gitignore=existing)
        store.register('org/acme', 'an ask')
        assert ignore_writes(written) == []
    written = _wire_register(monkeypatch, refs=[], present=[], gitignore=None)
    store.register('org/acme', 'an ask')
    assert len(ignore_writes(written)) == 1

@intent('INT-FC-R37')
def test_register_names_the_empty_repo_instead_of_surfacing_a_bare_409(monkeypatch, _use_vendored_establish):
    """The git-data API answers 409 on a repository with no commits, and a raw HTTPError
    would surface as a bare 500. Register turns it into the endpoint's clear-error shape
    naming what the operator can do; nothing lands past the refused mint."""
    written = _wire_register(monkeypatch, refs=[], present=[], empty_repo=True)
    with pytest.raises(RuntimeError, match='no commits'):
        GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'an ask')
    assert [(m, p) for m, p, _ in written if '/git/' in p] == []
