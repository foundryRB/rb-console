"""The archive path of establish: an existing application, uploaded as a zip, seeds the
repository born for it, so the Scope phase reads the app itself as the line's input
(the recast ground of REF-Delivery section 1; INT-FC-R148). Three seams: the archive's
own screening (pure), the service's ordering and refusals, and the GitHub store's one
seed commit over the auto-init tip.
"""
from capability_support import with_lifecycle
from capability_support import command_kwargs
import base64
import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pytest_intent import intent
from orchestrator.adapters.inbound.http.app import create_app
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from capability_support import make_capabilities
from orchestrator.domain.exceptions.source_archive_error import SourceArchiveError
from orchestrator.domain.source_archive import unpack_source_archive

def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, data in files.items():
            archive.writestr(path, data)
    return buf.getvalue()
APP = {'app-main/package.json': b'{"name":"app"}\n', 'app-main/src/App.tsx': b'export const App = () => null;\n', 'app-main/node_modules/left-pad/index.js': b'module.exports = 1;\n', 'app-main/dist/bundle.js': b'built\n', 'app-main/public/logo.png': b'\x89PNG\r\n\x1a\n\x00\x00binary', 'app-main/.env.example': b'API_URL=\n'}

@intent('INT-FC-R148')
def test_unpack_strips_the_wrapping_folder_and_skips_vendored_and_built_trees():
    files = unpack_source_archive(_zip(APP))
    assert [f.path for f in files] == ['.env.example', 'package.json', 'public/logo.png', 'src/App.tsx']
    by_path = {f.path: f for f in files}
    assert by_path['src/App.tsx'].text is not None and by_path['src/App.tsx'].text.startswith('export')
    assert by_path['public/logo.png'].text is None

@intent('INT-FC-R148')
def test_unpack_refuses_env_files_and_secret_shaped_strings_by_name():
    with pytest.raises(SourceArchiveError) as env:
        unpack_source_archive(_zip({'src/a.ts': b'ok', '.env': b'KEY=1\n', '.env.local': b'K=2\n'}))
    assert '.env' in str(env.value) and '.env.local' in str(env.value)
    with pytest.raises(SourceArchiveError) as leak:
        unpack_source_archive(_zip({'src/a.ts': b'ok', 'src/config.ts': b"const key = 'sk-abcdefghijklmnopqrstuvwxyz123456';\n", 'deploy/id_rsa': b'-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n'}))
    message = str(leak.value)
    assert 'src/config.ts' in message and 'deploy/id_rsa' in message
    assert 'src/a.ts' not in message

@intent('INT-FC-R148')
def test_unpack_refuses_escapes_emptiness_and_non_zips():
    with pytest.raises(SourceArchiveError, match='escape'):
        unpack_source_archive(_zip({'../outside.txt': b'x', 'src/a.ts': b'ok'}))
    with pytest.raises(SourceArchiveError, match='no source files'):
        unpack_source_archive(_zip({'node_modules/x.js': b'x', '.DS_Store': b''}))
    with pytest.raises(SourceArchiveError, match='not a zip'):
        unpack_source_archive(b'definitely not a zip')

class _Repos:
    """A store recording the order of its acts, holding the repos named in ``holding``."""

    def __init__(self, holding=()):
        self.log = []
        self._holding = set(holding)

    def list_delivery_repos(self):
        return []

    def repo_exists(self, target):
        return target.split('/')[-1] in self._holding

    def ensure(self, target):
        self.log.append(('ensure', target))
        return f'org/{target}'

    def register(self, workspace, request='', source=(), source_name=''):
        entry = ('register', workspace, request)
        if source:
            entry = entry + ([f.path for f in source], source_name)
        self.log.append(entry)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class _Studios:

    def __init__(self):
        self.calls = []

    def create_app_repo(self, name, display_name, description, repo=''):
        self.calls.append(name)
        return {}

@intent('INT-FC-R148')
def test_establish_templates_the_repo_and_lands_the_archive_on_the_scratch():
    """The archive never touches the default branch. main is born templated exactly
    as a greenfield is; the source lands under _recast/ on the line's own orphan
    scratch ref - where no workflow triggers, and which close tags then removes."""
    repos, studios = (_Repos(), _Studios())
    make_capabilities(repos, studios=studios).establish.execute('acme-app', 'Recast our app onto the foundry', _zip(APP), 'acme-app.zip', **command_kwargs('acme-app'))
    assert studios.calls == ['acme-app']
    assert [entry[0] for entry in repos.log] == ['ensure', 'register']
    _, workspace, request, paths, label = repos.log[1]
    assert workspace == 'org/acme-app'
    assert request == 'Recast our app onto the foundry'
    assert 'src/App.tsx' in paths and 'node_modules/left-pad/index.js' not in paths
    assert len(paths) == 4 and label == 'acme-app.zip'

@intent('INT-FC-R148')
def test_establish_recasts_into_a_repository_that_is_there():
    """The refusal that guarded an existing repository existed only because the
    archive used to overwrite its default branch. On the scratch it overwrites
    nothing, so an existing repository is adopted and recast."""
    repos, studios = (_Repos(holding=['acme-app']), _Studios())
    make_capabilities(repos, studios=studios).establish.execute('acme-app', 'Recast it', _zip(APP), 'a.zip', **command_kwargs('acme-app'))
    assert [entry[0] for entry in repos.log] == ['ensure', 'register']
    assert len(repos.log[1][3]) == 4

@intent('INT-FC-R148')
def test_establish_screens_the_archive_before_creating_anything():
    repos = _Repos()
    with pytest.raises(SourceArchiveError, match='env files'):
        make_capabilities(repos).establish.execute('acme-app', '', _zip({'src/a.ts': b'ok', '.env': b'K=1\n'}), **command_kwargs('acme-app'))
    assert repos.log == []

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

def _wire_register(monkeypatch):
    """Route urlopen for the register path over org/acme: no live delivery/* line yet,
    no .gitignore yet. Records every write. The skeleton and the request doc the mint
    carries are the playbook helper's own, loaded from a path only a pod has; here the
    loader is pointed at the vendored copy, the same bytes the image bakes in."""
    import orchestrator.adapters.outbound.github.github_repo_store as store_module
    vendored = Path(__file__).resolve().parents[1] / 'devops' / 'vendor' / 'establish_scratch.py'
    monkeypatch.setattr(store_module, '_ESTABLISH_HELPER', str(vendored))
    written = []

    def urlopen(req, timeout=0):
        method = req.get_method()
        path = req.full_url.replace('https://api.github.com', '')
        if method == 'GET':
            if path.endswith('/git/matching-refs/heads/delivery/'):
                return _Resp([])
            raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
        body = json.loads(req.data.decode()) if req.data else {}
        written.append((method, path, body))
        if path.endswith('/git/blobs'):
            return _Resp({'sha': f'blob{len(written)}'})
        if path.endswith('/git/trees'):
            return _Resp({'sha': 'tree0'})
        if path.endswith('/git/commits'):
            return _Resp({'sha': 'commit0'})
        if path.endswith('/git/tags'):
            return _Resp({'sha': 'tag0'})
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout=timeout))
    return written

@intent('INT-FC-R148')
def test_register_lands_the_source_under_recast_on_the_scratch(monkeypatch):
    """The source is part of the ONE root tree the orphan is minted from - text inline,
    a binary as a blob first, every path under _recast/ - and no write touches main."""
    written = _wire_register(monkeypatch)
    files = unpack_source_archive(_zip(APP))
    GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'Recast it', files, 'acme.zip')
    tree = next((b for _, p, b in written if p.endswith('/git/trees')))
    paths = [e['path'] for e in tree['tree']]
    assert 'README.md' in paths and 'request.md' in paths
    assert '_recast/src/App.tsx' in paths and '_recast/public/logo.png' in paths
    assert all((p.startswith('_recast/') for p in paths if p not in ('README.md', 'request.md')))
    logo = next((e for e in tree['tree'] if e['path'] == '_recast/public/logo.png'))
    assert 'sha' in logo and 'content' not in logo
    commit = next((b for _, p, b in written if p.endswith('/git/commits')))
    assert commit['parents'] == []
    assert 'acme.zip' in commit['message'] and '_recast/' in commit['message']
    assert not any(('/refs/heads/main' in p for _, p, _ in written))

@intent('INT-FC-R149')
def test_the_register_commit_carries_the_seed_tag(monkeypatch):
    """seed/<slug> on the register commit - the one that carries _recast/ - so the seed
    reads off the repo exactly as before, and the tag outlives the scratch ref that
    close removes, keeping the source reachable."""
    written = _wire_register(monkeypatch)
    files = unpack_source_archive(_zip(APP))
    GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'Recast it', files, 'acme.zip')
    tag = next((b for _, p, b in written if p.endswith('/git/tags')))
    assert tag['tag'] == 'seed/acme' and tag['object'] == 'commit0' and (tag['type'] == 'commit')
    ref = next((b for _, p, b in written if p.endswith('/git/refs') and b.get('ref', '').startswith('refs/tags/')))
    assert ref == {'ref': 'refs/tags/seed/acme', 'sha': 'tag0'}
    order = [p for _, p, _ in written]
    assert order.index('/repos/org/acme/git/commits') < order.index('/repos/org/acme/git/tags')

@intent('INT-FC-R149')
def test_register_without_a_source_mints_no_seed_tag(monkeypatch):
    """A greenfield's scratch carries no _recast/ and no seed tag: the seed reads new."""
    written = _wire_register(monkeypatch)
    GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'Build it')
    assert not any((p.endswith('/git/tags') for _, p, _ in written))
    tree = next((b for _, p, b in written if p.endswith('/git/trees')))
    assert all((not e['path'].startswith('_recast/') for e in tree['tree']))

@intent('INT-FC-R148')
def test_register_refuses_a_source_over_a_live_line(monkeypatch):
    """A source seeds only a scratch minted in this establish. Over a line that already
    exists it would land beside records that line has already written, so the store
    refuses before a byte of it goes up, naming the line to close first."""
    written = []

    def urlopen(req, timeout=0):
        path = req.full_url.replace('https://api.github.com', '')
        if req.get_method() == 'GET' and path.endswith('/git/matching-refs/heads/delivery/'):
            return _Resp([{'ref': 'refs/heads/delivery/2026-09-08', 'object': {'sha': 'tip0'}}])
        if req.get_method() == 'GET' and path.endswith('/contents/.gitignore'):
            return _Resp({'content': base64.b64encode(b'.delivery/\n').decode(), 'sha': 'ignore-blob'})
        if req.get_method() == 'GET' and path == '/repos/org/acme':
            return _Resp({'full_name': 'org/acme'})
        if req.get_method() != 'GET':
            written.append(path)
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout=timeout))
    with pytest.raises(RuntimeError, match='already carries a live line'):
        GitHubRepoStore('org', lambda: 'tok').register('org/acme', 'Recast it', unpack_source_archive(_zip(APP)), 'acme.zip')
    assert not any(('/git/' in p for p in written))

class _FileRepos:
    """A local store: the workspace is a directory, the seed writes the files into it."""

    def __init__(self, tmp):
        self.tmp = Path(tmp)

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        path = self.tmp / target
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def register(self, workspace, request='', source=(), source_name=''):
        scratch = Path(workspace) / '.delivery'
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / 'README.md').write_text('s', encoding='utf-8')
        if request:
            (scratch / 'request.md').write_text(request, encoding='utf-8')
        for file in source:
            dst = scratch / '_recast' / file.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(file.data)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

@intent('INT-FC-R148')
def test_establish_over_http_takes_the_archive_as_base64(tmp_path):
    client = TestClient(create_app(make_capabilities(_FileRepos(tmp_path))))
    body = {'target': 'acme', 'request': 'Recast it', 'source_archive': base64.b64encode(_zip(APP)).decode(), 'source_name': 'acme.zip'}
    response = client.post('/api/establish', json=body)
    assert response.status_code == 200 and response.json()['exists'] is True
    recast = tmp_path / 'acme' / '.delivery' / '_recast'
    assert (recast / 'src' / 'App.tsx').exists()
    assert not (recast / 'node_modules').exists()
    assert not (tmp_path / 'acme' / 'src').exists()
    assert 'Recast' in (tmp_path / 'acme' / '.delivery' / 'request.md').read_text(encoding='utf-8')

@intent('INT-FC-R148')
def test_establish_over_http_answers_422_for_a_bad_archive(tmp_path):
    client = TestClient(create_app(make_capabilities(_FileRepos(tmp_path))))
    response = client.post('/api/establish', json={'target': 'acme', 'source_archive': 'not base64!!'})
    assert response.status_code == 422 and 'base64' in response.json()['detail']
    leaking = base64.b64encode(_zip({'src/a.ts': b'ok', '.env': b'K=1\n'})).decode()
    response = client.post('/api/establish', json={'target': 'acme', 'source_archive': leaking})
    assert response.status_code == 422 and '.env' in response.json()['detail']
    assert not (tmp_path / 'acme').exists()
