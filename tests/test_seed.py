"""A delivery's seed - what the line grows from - is derived from the repo's tags and never
declared (INT-FC-R149): a delivered tag reads follow-on, a seed tag reads recast, neither
reads new, and a namespace the source cannot read reports unavailable rather than inferring new."""
import base64
import json
import pytest
from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle, lifecycle_digest
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE, CURRENT_PLAYBOOK_REF
from urllib.parse import quote
from pytest_intent import intent
from orchestrator.adapters.inbound.http.mappers.delivery import state_dto
from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource
from orchestrator.domain.delivery import SEED_FOLLOW_ON, SEED_NEW, SEED_RECAST, derive_seed
_REF = 'delivery/2026-09-04'
_QREF = quote(_REF, safe='')

@intent('INT-FC-R149')
def test_the_seed_derives_from_the_two_tags_and_the_delivered_tag_wins():
    assert derive_seed(has_delivered_tag=False, has_seed_tag=False) == SEED_NEW
    assert derive_seed(has_delivered_tag=False, has_seed_tag=True) == SEED_RECAST
    assert derive_seed(has_delivered_tag=True, has_seed_tag=False) == SEED_FOLLOW_ON
    assert derive_seed(has_delivered_tag=True, has_seed_tag=True) == SEED_FOLLOW_ON

def _source(tags: dict[str, list] | None, unreadable: bool=False):
    """A GitHub source over one delivery repo (example-org/acme) whose tag namespaces answer
    ``tags`` ({'delivered': [...], 'seed': [...]}); ``unreadable`` makes both raise."""
    reads: list[str] = []

    def fake_get(path, token):
        reads.append(path)
        if path == '/repos/example-org/acme':
            return {'id': 42}
        if path == '/repos/example-org/acme/contents/config.json?ref=tip0':
            payload = {**encode_lifecycle(CURRENT_LIFECYCLE), 'digest': lifecycle_digest(CURRENT_LIFECYCLE), 'source_ref': CURRENT_PLAYBOOK_REF}
            return {'content': base64.b64encode(json.dumps({'lifecycle': payload}).encode()).decode()}
        if path.startswith('/orgs/example-org/repos'):
            return [{'full_name': 'example-org/acme', 'name': 'acme', 'id': 42, 'pushed_at': 't1', 'topics': [], 'archived': False}, {'full_name': 'example-org/bare', 'name': 'bare', 'id': 43, 'pushed_at': 't2', 'topics': [], 'archived': False}]
        if path == '/repos/example-org/acme/git/matching-refs/heads/delivery/':
            return [{'ref': f'refs/heads/{_REF}', 'object': {'sha': 'tip0'}}]
        if path == '/repos/example-org/bare/git/matching-refs/heads/delivery/':
            return []
        if path == f'/repos/example-org/acme/contents?ref=tip0':
            return [{'name': 'proposal.md'}, {'name': 'config.json'}]
        if path == f'/repos/example-org/acme/contents/proposal.md?ref=tip0':
            return {'content': base64.b64encode(b'---\nstatus: complete\ngate: proposal\nsigned: 2026-09-01\n---\nProposal').decode()}
        if path.startswith('/repos/example-org/acme/git/matching-refs/tags/'):
            if unreadable:
                raise SourceUnavailable('tag namespace unavailable')
            namespace = path.rsplit('/', 2)[-2]
            return (tags or {}).get(namespace, [])
        raise RuntimeError(f'404 {path}')
    src = GitHubDeliverySource('example-org', lambda: 'tok')
    src._get = fake_get
    return (src, reads)

@intent('INT-FC-R149')
def test_the_source_reads_the_seed_off_the_tags_for_a_repo_that_carries_a_line():
    delivered = [{'ref': 'refs/tags/delivered/acme/P1', 'object': {'sha': 't1'}}]
    seeded = [{'ref': 'refs/tags/seed/acme', 'object': {'sha': 's1'}}]
    for tags, expected in (({}, SEED_NEW), ({'seed': seeded}, SEED_RECAST), ({'delivered': delivered}, SEED_FOLLOW_ON), ({'delivered': delivered, 'seed': seeded}, SEED_FOLLOW_ON)):
        src, reads = _source(tags)
        states = src.scan()
        assert [s.repo for s in states] == ['example-org/acme']
        assert states[0].seed == expected
        assert src.state_of('example-org/acme').seed == expected
        assert not any((p.startswith('/repos/example-org/bare/git/matching-refs/tags/') for p in reads))
        assert state_dto(states[0])['seed'] == expected

@intent('INT-FC-R149')
def test_an_unreadable_tag_namespace_refuses_observation_never_infers_new():
    src, _ = _source({}, unreadable=True)
    with pytest.raises(SourceUnavailable):
        src.scan()
    with pytest.raises(SourceUnavailable):
        src.state_of('example-org/acme')
