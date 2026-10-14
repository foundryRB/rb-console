"""The store's Close-line act over the git-data API: mint the annotated
delivered/<slug>/P<n> tag on the scratch ref's tip and push it, THEN delete the
delivery/<line-id> ref - tag before delete, mandatorily, because the annotated tag is
what keeps the orphan history reachable (an untagged delete makes the line's whole
record trail garbage-collectable). The default branch is never touched: the scratch
does not live on it."""
import json
import urllib.error
import urllib.request
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
_REF = 'delivery/2026-08-18'
_PROPOSAL = '---\nphase: scope\ndelivers: P2\nsigned: 2026-08-13\n---\n\n# Proposal\n'
_ATTESTS = '0a1b2c3d4e5f60718293a4b5c6d7e8f901234567'
_BUILD = f'---\nphase: build+ship\nstatus: complete\nattests: {_ATTESTS}\nsigned: 2026-08-15\n---\n\n# Build\n'

class _Resp:
    headers = {}
    status = 200

    def __init__(self, body):
        self._body = body
        self.headers = {}
        self.status = 200

    def read(self, *_args):
        return json.dumps(self._body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

def _wire(monkeypatch, refs, files=None, tag_fails=False, tag_at=None, proposal_error=None, build_error=None):
    """Serve the repo's delivery/* namespace and scratch blobs; record every mutating
    call as (method, path, body) in order. ``tag_fails`` makes the annotated-tag POST
    blow up, to prove the ref outlives a close whose tag never landed. ``tag_at`` is the
    commit an already-existing delivered/* tag ultimately points at (served as an
    annotated tag object, so the dereference is exercised); None means no such tag.
    ``proposal_error`` / ``build_error`` are raised from that record's read, to model a
    transport failure distinct from the record being absent (a 404)."""
    import base64
    sent: list[tuple[str, str, dict]] = []
    files = files or {}

    def urlopen(req, timeout=0):
        method = req.get_method()
        path = req.full_url.replace('https://api.github.com', '')
        if method == 'GET':
            if path == '/repos/org/acme':
                return _Resp({'node_id': 'repository-node', 'full_name': 'org/acme'})
            if path.endswith('/git/matching-refs/heads/delivery/'):
                return _Resp([{'ref': f'refs/heads/{r}', 'object': {'sha': f'tip-{r}'}} for r in refs])
            if '/git/ref/tags/' in path:
                if tag_at is None:
                    raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
                return _Resp({'object': {'type': 'tag', 'sha': 'tagobj-existing'}})
            if path.endswith('/git/tags/tagobj-existing'):
                return _Resp({'object': {'sha': tag_at, 'type': 'commit'}})
            rel = path.split('/contents/', 1)[1].partition('?')[0] if '/contents/' in path else ''
            if rel == 'proposal.md' and proposal_error is not None:
                raise proposal_error
            if rel == 'build.md' and build_error is not None:
                raise build_error
            if rel in files:
                return _Resp({'content': base64.b64encode(files[rel].encode()).decode()})
            raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
        body = json.loads(req.data.decode()) if req.data else {}
        if path.endswith('/git/tags') and tag_fails:
            raise RuntimeError('422 tag refused')
        sent.append((method, path, body))
        if path == '/graphql':
            return _Resp({'data': {'updateRefs': {'clientMutationId': body['variables']['input']['clientMutationId']}}})
        if path.endswith('/git/tags'):
            return _Resp({'sha': 'tagobj0'})
        if path.endswith('/git/refs'):
            return _Resp({'ref': body['ref'], 'object': {'sha': body['sha'], 'type': 'tag'}})
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout))
    return sent

def _store() -> GitHubRepoStore:
    return GitHubRepoStore('org', lambda: 'tok')

@intent('INT-FC-R79')
def test_close_tags_the_tip_then_deletes_the_ref_in_that_order(monkeypatch):
    sent = _wire(monkeypatch, refs=[_REF], files={'proposal.md': _PROPOSAL})
    _store().close_line('org/acme')
    kinds = [(m, p.rsplit('/repos/org/acme', 1)[-1]) for m, p, _ in sent]
    assert kinds == [('POST', '/git/tags'), ('POST', '/git/refs'), ('POST', '/graphql')]
    tag_body = sent[0][2]
    assert tag_body['tag'] == 'delivered/acme/P2'
    assert tag_body['object'] == f'tip-{_REF}' and tag_body['type'] == 'commit'
    assert sent[1][2] == {'ref': 'refs/tags/delivered/acme/P2', 'sha': 'tagobj0'}
    assert sent[2][2]['variables']['input']['refUpdates'] == [
        {'name': f'refs/heads/{_REF}', 'beforeOid': f'tip-{_REF}', 'afterOid': '0' * 40},
    ]

@intent('INT-FC-R79')
def test_the_annotation_carries_the_attested_sha_from_the_build_record(monkeypatch):
    """A follow-on reads the delivered marker from the tag OBJECT - existence, phase,
    date, attests - never the tag's tree (REF-FollowOn), so the close carries build.md's
    attests: pin into the annotation: the close line first, a blank line, the field."""
    sent = _wire(monkeypatch, refs=[_REF], files={'proposal.md': _PROPOSAL, 'build.md': _BUILD})
    _store().close_line('org/acme')
    message = sent[0][2]['message']
    first, sep, rest = message.partition('\n\n')
    assert first == f'delivery: close line (delivered/acme/P2 anchors the {_REF} record trail)'
    assert sep and rest == f'attests: {_ATTESTS}'

@intent('INT-FC-R79')
def test_a_line_that_never_built_closes_without_an_attests_line(monkeypatch):
    """No build.md (abandoned pre-build), or a build record that pinned nothing: the
    annotation carries no attests line - absence is honest, and a fabricated value
    would point a follow-on at a commit nothing ever verified live."""
    for files in ({'proposal.md': _PROPOSAL}, {'proposal.md': _PROPOSAL, 'build.md': '---\nphase: build+ship\n---\n\n# Build\n'}):
        sent = _wire(monkeypatch, refs=[_REF], files=dict(files))
        _store().close_line('org/acme')
        assert 'attests' not in sent[0][2]['message']

@intent('INT-FC-R79')
def test_a_transport_error_reading_the_build_record_aborts_the_close(monkeypatch):
    """Only a 404 means the build record is absent; any other read failure aborts the
    close before anything lands, because a transient blip must not mint a permanently
    wrong annotation (the same rule the delivers: pin read follows)."""
    sent = _wire(monkeypatch, refs=[_REF], files={'proposal.md': _PROPOSAL}, build_error=urllib.error.HTTPError('u', 502, 'Bad Gateway', {}, None))
    with pytest.raises(SourceUnavailable):
        _store().close_line('org/acme')
    assert sent == []

@intent('INT-FC-R79')
def test_a_close_whose_tag_cannot_land_leaves_the_ref_alone(monkeypatch):
    """The ordering is a guarantee, not a habit: no tag, no delete. Deleting an untagged
    orphan branch would make the line's history collectable, so the close aborts with
    the ref still in place."""
    sent = _wire(monkeypatch, refs=[_REF], files={'proposal.md': _PROPOSAL}, tag_fails=True)
    with pytest.raises(RuntimeError):
        _store().close_line('org/acme')
    assert all((m != 'DELETE' for m, _, _ in sent))

@intent('INT-FC-R79')
def test_close_is_idempotent_and_refuses_the_ref_anomaly(monkeypatch):
    sent = _wire(monkeypatch, refs=[])
    _store().close_line('org/acme')
    assert sent == []
    sent = _wire(monkeypatch, refs=['delivery/2026-08-01', _REF])
    with pytest.raises(ValueError, match='exactly one'):
        _store().close_line('org/acme')
    assert sent == []

@intent('INT-FC-R79')
def test_a_line_with_no_delivers_pin_still_gets_a_well_formed_tag(monkeypatch):
    """A line abandoned before scope pinned `delivers:` (or whose proposal is missing)
    closes under P1 rather than refusing or minting a malformed name."""
    sent = _wire(monkeypatch, refs=[_REF])
    _store().close_line('org/acme')
    assert sent[0][2]['tag'] == 'delivered/acme/P1'

@intent('INT-FC-R79')
def test_a_half_done_close_resumes_at_the_delete(monkeypatch):
    """The tag landed on a previous attempt and the ref delete did not (the pod died
    between the two). The existing tag already anchors this exact tip, so the close
    resumes: no second tag, straight to the delete."""
    sent = _wire(monkeypatch, refs=[_REF], files={'proposal.md': _PROPOSAL}, tag_at=f'tip-{_REF}')
    _store().close_line('org/acme')
    assert [(m, p) for m, p, _ in sent] == [('POST', '/graphql')]
    assert sent[0][2]['variables']['input']['refUpdates'] == [
        {'name': f'refs/heads/{_REF}', 'beforeOid': f'tip-{_REF}', 'afterOid': '0' * 40},
    ]

@intent('INT-FC-R79')
def test_a_tag_pointing_elsewhere_refuses_the_close_naming_both_shas(monkeypatch):
    """The name is taken by a DIFFERENT close (an earlier line delivering the same
    phase, or a hand-minted tag). Overwriting would orphan whichever history that tag
    anchors, so the close refuses - naming both commits - and deletes nothing."""
    sent = _wire(monkeypatch, refs=[_REF], files={'proposal.md': _PROPOSAL}, tag_at='elsewhere0')
    with pytest.raises(ValueError) as err:
        _store().close_line('org/acme')
    assert 'elsewhere0' in str(err.value) and f'tip-{_REF}' in str(err.value)
    assert sent == []

@intent('INT-FC-R79')
def test_a_transport_error_reading_the_phase_pin_aborts_the_close(monkeypatch):
    """Only a 404 means the proposal (and its delivers: pin) is absent; any other read
    failure aborts the close before anything lands, because a transient network blip
    must not mint a permanently mislabeled delivered/<slug>/P1 tag."""
    sent = _wire(monkeypatch, refs=[_REF], proposal_error=urllib.error.HTTPError('u', 502, 'Bad Gateway', {}, None))
    with pytest.raises(SourceUnavailable):
        _store().close_line('org/acme')
    assert sent == []
