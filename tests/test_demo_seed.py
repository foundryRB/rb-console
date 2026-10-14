"""A demo line's seed is derived from its name and the org, never declared (INT-FC-R153):
a repo named demo-<x> reads demo when the org holds <x> as a line, carries <x> beside the
seed as demo_of, wins over its own tags, and reports unavailable when the source cannot be read."""
import base64
import json
import pytest
from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle, lifecycle_digest
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE, CURRENT_PLAYBOOK_REF
import urllib.error
from urllib.parse import quote
from pytest_intent import intent
from orchestrator.adapters.inbound.http.mappers.delivery import state_dto
from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource
from orchestrator.domain.delivery import SEED_DEMO, SEED_FOLLOW_ON, SEED_NEW, demo_source_name, derive_seed
_REF = 'delivery/2026-09-08'
_QREF = quote(_REF, safe='')

@intent('INT-FC-R153')
def test_the_demo_source_is_read_off_the_name_alone():
    assert demo_source_name('example-org/demo-acme') == 'acme'
    assert demo_source_name('demo-org-acme') == 'org-acme'
    assert demo_source_name('example-org/acme') == ''
    assert demo_source_name('example-org/demonstration') == ''
    assert demo_source_name('demo-') == ''

@intent('INT-FC-R153')
def test_a_demo_wins_over_the_repo_s_own_tags():
    assert derive_seed(has_delivered_tag=False, has_seed_tag=False, demo_source='example-org/acme') == SEED_DEMO
    assert derive_seed(has_delivered_tag=True, has_seed_tag=True, demo_source='example-org/acme') == SEED_DEMO
    assert derive_seed(has_delivered_tag=True, has_seed_tag=False, demo_source='') == SEED_FOLLOW_ON

def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError('https://api.github.com/x', code, 'refused', {}, None)

def _source(source_heads, source_tags, *, source_fails=None):
    """A GitHub source over an org holding the demo repo example-org/demo-acme (a live line) and
    its source example-org/acme, whose delivery heads and delivered tags answer as given; a
    ``source_fails`` exception makes every read of the source raise it."""
    reads: list[str] = []

    def fake_get(path, token):
        reads.append(path)
        if path == '/repos/example-org/demo-acme':
            return {'id': 42}
        if path == '/repos/example-org/demo-acme/contents/config.json?ref=tip0':
            payload = {**encode_lifecycle(CURRENT_LIFECYCLE), 'digest': lifecycle_digest(CURRENT_LIFECYCLE), 'source_ref': CURRENT_PLAYBOOK_REF}
            return {'content': base64.b64encode(json.dumps({'lifecycle': payload}).encode()).decode()}
        if path.startswith('/orgs/example-org/repos'):
            return [{'full_name': 'example-org/demo-acme', 'name': 'demo-acme', 'id': 42, 'pushed_at': 't1', 'topics': [], 'archived': False}, {'full_name': 'example-org/acme', 'name': 'acme', 'id': 43, 'pushed_at': 't2', 'topics': [], 'archived': False}]
        if path == '/repos/example-org/demo-acme/git/matching-refs/heads/delivery/':
            return [{'ref': f'refs/heads/{_REF}', 'object': {'sha': 'tip0'}}]
        if path == f'/repos/example-org/demo-acme/contents?ref=tip0':
            return [{'name': 'proposal.md'}, {'name': 'config.json'}]
        if path == f'/repos/example-org/demo-acme/contents/proposal.md?ref=tip0':
            return {'content': base64.b64encode(b'---\nstatus: complete\ngate: proposal\nsigned: 2026-09-08\n---\nProposal').decode()}
        if path.startswith('/repos/example-org/demo-acme/git/matching-refs/tags/'):
            return []
        if path == '/repos/example-org/acme':
            return {'id': 43}
        if path.startswith('/repos/example-org/acme/'):
            if source_fails is not None:
                raise source_fails
            if path == '/repos/example-org/acme/git/matching-refs/heads/delivery/':
                return source_heads
            if path == '/repos/example-org/acme/git/matching-refs/tags/delivered/':
                return source_tags
            if path.startswith('/repos/example-org/acme/git/matching-refs/tags/'):
                return []
            if path == '/repos/example-org/acme/contents?ref=s':
                return [{'name': 'config.json'}]
            if path == '/repos/example-org/acme/contents/config.json?ref=s':
                payload = {**encode_lifecycle(CURRENT_LIFECYCLE), 'digest': lifecycle_digest(CURRENT_LIFECYCLE), 'source_ref': CURRENT_PLAYBOOK_REF}
                return {'content': base64.b64encode(json.dumps({'lifecycle': payload}).encode()).decode()}
        raise RuntimeError(f'404 {path}')
    src = GitHubDeliverySource('example-org', lambda: 'tok')
    src._get = fake_get
    return (src, reads)

@intent('INT-FC-R153')
def test_a_demo_named_repo_over_a_line_the_org_holds_reads_demo_and_names_its_source():
    head = [{'ref': f'refs/heads/{_REF}', 'object': {'sha': 's'}}]
    tag = [{'ref': 'refs/tags/delivered/acme/P1', 'object': {'sha': 't'}}]
    for heads, tags in ((head, []), ([], tag), (head, tag)):
        src, _ = _source(heads, tags)
        state = src.state_of('example-org/demo-acme')
        assert state.seed == SEED_DEMO
        assert state.demo_of == 'example-org/acme'
        assert state_dto(state)['demo_of'] == 'example-org/acme'
        scanned = {s.repo: s for s in src.scan()}
        assert scanned['example-org/demo-acme'].seed == SEED_DEMO
        assert scanned['example-org/demo-acme'].demo_of == 'example-org/acme'

@intent('INT-FC-R153')
def test_a_demo_named_repo_whose_source_is_no_line_reads_by_its_own_tags():
    src, _ = _source([], [])
    state = src.state_of('example-org/demo-acme')
    assert state.seed == SEED_NEW
    assert state.demo_of == ''

@intent('INT-FC-R153')
def test_a_source_that_is_absent_is_no_line_but_one_that_cannot_be_read_is_unknown():
    absent, _ = _source([], [], source_fails=_http_error(404))
    assert absent.state_of('example-org/demo-acme').seed == SEED_NEW
    for failure in (_http_error(403), OSError('connection refused')):
        unreadable, _ = _source([], [], source_fails=failure)
        with pytest.raises(SourceUnavailable):
            unreadable.state_of('example-org/demo-acme')

@intent('INT-FC-R153')
def test_only_a_prefixed_name_pays_the_source_read():
    head = [{'ref': f'refs/heads/{_REF}', 'object': {'sha': 's'}}]
    src, reads = _source(head, [])
    src.state_of('example-org/demo-acme')
    assert any((p.startswith('/repos/example-org/acme/git/matching-refs/') for p in reads))
    reads.clear()
    src.state_of('example-org/acme')
    assert reads and all((p == '/repos/example-org/acme' or p.startswith('/repos/example-org/acme/') for p in reads))
