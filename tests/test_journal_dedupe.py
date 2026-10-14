"""A retried drive must not journal the same gate feedback twice.

One operator correction, issued once, landed twice byte-identically (knight-fight
``3f38792``/``a891c47``, #69): the drive is record-then-run, so a form re-submit or a
retry after a failed submit re-sends the identical entry, and ``append_journal``
appended it again. Two identical sections read as two consecutive re-drives to the
stale-re-drive cap. The guard: an identical block already at the journal's tail is
the retry, not a second event - skip it; the same block deeper in the file (entries
between) is a genuine repeat and still appends.
"""
import base64
import json
import urllib.error
import urllib.request
from urllib.parse import quote
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
_REF = 'delivery/2026-08-05'
_ENTRY = '## proposal gate: re-driven 2026-08-05\n\nreprice REQ-3'

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

def _wire(monkeypatch, files: dict[str, str]):
    """Serve ``files`` (branch-root path -> text) as contents-API blobs on the line's
    ref; record every write as (path, decoded content) in order."""
    sent: list[tuple[str, str]] = []

    def urlopen(req, timeout=0):
        path = req.full_url.replace('https://api.github.com', '')
        if req.get_method() == 'GET' and path.endswith('/git/matching-refs/heads/delivery/'):
            return _Resp([{'ref': f'refs/heads/{_REF}', 'object': {'sha': 'tip'}}])
        rel = path.split('/contents/', 1)[1] if '/contents/' in path else ''
        rel, _, query = rel.partition('?')
        if req.get_method() == 'GET':
            assert f"ref={quote(_REF, safe='')}" in query, f'a scratch read must follow the ref: {path}'
            if rel not in files:
                raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
            return _Resp({'content': base64.b64encode(files[rel].encode()).decode(), 'sha': f'sha-{rel}'})
        body = json.loads(req.data.decode())
        assert body.get('branch') == _REF, f'a scratch write must name the ref: {path}'
        text = base64.b64decode(body['content']).decode()
        sent.append((rel, text))
        files[rel] = text
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout=timeout))
    return sent

def _store() -> GitHubRepoStore:
    return GitHubRepoStore('Example-Org-Of-Engineering', lambda: 't0ken')

def test_a_retried_identical_entry_is_not_appended(monkeypatch):
    sent = _wire(monkeypatch, {'journal.md': f'# Journal\n\n{_ENTRY}\n'})
    _store().append_journal('knight-fight', _ENTRY)
    assert sent == [], 'an identical tail block is a retried write, not a second event'

def test_a_different_entry_still_appends(monkeypatch):
    sent = _wire(monkeypatch, {'journal.md': f'# Journal\n\n{_ENTRY}\n'})
    _store().append_journal('knight-fight', '## proposal gate: re-driven 2026-08-05\n\ndrop REQ-9')
    written = dict(sent)
    assert 'drop REQ-9' in written['journal.md']
    assert 'reprice REQ-3' in written['journal.md']

def test_an_identical_block_behind_the_tail_is_a_genuine_repeat(monkeypatch):
    journal = f'# Journal\n\n{_ENTRY}\n\n## design gate: re-driven 2026-08-05\n\nnew logo\n'
    sent = _wire(monkeypatch, {'journal.md': journal})
    _store().append_journal('knight-fight', _ENTRY)
    written = dict(sent)
    assert written['journal.md'].count('reprice REQ-3') == 2

def test_an_absent_journal_is_still_created_around_the_entry(monkeypatch):
    sent = _wire(monkeypatch, {})
    _store().append_journal('knight-fight', _ENTRY)
    written = dict(sent)
    assert written['journal.md'].startswith('# Delivery journal')
    assert 'reprice REQ-3' in written['journal.md']
