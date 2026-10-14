from maintenance_fixtures import semantic_check, semantic_comment, semantic_issue, semantic_pr, semantic_review
"""The maintenance mode's pure derivations: positions (INT-FC-R58), the release
train (INT-FC-R59), the verdict (INT-FC-R66), the ceremony modes (INT-FC-R64),
the one-shot merge gate's pure rows (with the service half in
test_maintenance_service.py), and the fleet inbox (INT-FC-R68)."""
from pytest_intent import intent
from orchestrator.application.fleet_inbox import derive_inbox
from orchestrator.domain.services.maintenance_judge import MAX_RESOLVE_ATTEMPTS, judge_one_shot, judge_resolve_fail
from orchestrator.domain.model.merge_gate import MergeGate
from orchestrator.domain.model.resolve_retry import ResolveRetry
from orchestrator.application import maintenance_modes
from orchestrator.application.maintenance_modes import is_contributor, parse_mode
from orchestrator.application.maintenance_resolver import DELIVERY_PROMPT_MARKER, checks_state, delivery_prompt_from_comments, delivery_prompt_of, derive_positions, read_ticket_signal
from orchestrator.application.release_train import derive_train, latest_version
from orchestrator.domain.services.fleet.app_identity import deployment_health
from orchestrator.application.services.maintenance.verdict import decide, derive_verdict
from orchestrator.domain.maintenance import CHECKS_UNKNOWN, VERDICT_AWAITING
from orchestrator.domain.model.issue_position import IssuePosition
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.maintenance_positions import MaintenancePositions
from orchestrator.domain.model.pr_position import PrPosition
from orchestrator.domain.model.release_train import ReleaseTrain
from tests.test_maintenance_service import _POSTED, _posted_as
import json
from dataclasses import asdict
from pathlib import Path
import pytest

def _issue(n, title, labels=()):
    return {'number': n, 'title': title, 'user': {'login': 'rafael'}, 'labels': [{'name': lb} for lb in labels], 'html_url': f'http://x/{n}'}

def _pr(n, title, author='fc-git', head='fix/7-x', sha='abc', body=''):
    return {'number': n, 'title': title, 'user': {'login': author}, 'body': body, 'head': {'ref': head, 'sha': sha}, 'html_url': f'http://x/pull/{n}'}

def _review(author, body, at='2026-07-11T10:00:00Z', assoc='MEMBER', state=_POSTED):
    """A GitHub review object. ``assoc`` is the author_association the verdict rule reads as
    write access; MEMBER by default, since every reviewer that matters here has it. ``state``
    is the review state, by default the one review-pr posts the body's verdict as."""
    return semantic_review({'user': {'login': author}, 'body': body, 'submitted_at': at, 'author_association': assoc, 'state': _posted_as(body) if state is _POSTED else state})

@intent('INT-FC-R58')
def test_positions_are_derived_pure_and_stored_nowhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = dict(repo='org/app', issues=[_issue(7, 'broken link'), {'number': 9, 'title': 'a PR in issue clothes', 'pull_request': {}, 'user': {'login': 'x'}}], prs=[_pr(12, 'fix: link (#7)')], reviews_by_pr={12: [_review('fc-review', 'solid\n\nVERDICT: PASS')]}, checks_by_pr={12: [{'status': 'completed', 'conclusion': 'success'}]}, tags=['v1.2.3'], unreleased_subjects=['fix: link (#7)'], git_user='fc-git', deployed='1.2.3', healthy=True)
    args["issues"] = tuple(semantic_issue(record) for record in args["issues"])
    args["prs"] = tuple(semantic_pr(record) for record in args["prs"])
    args["reviews_by_pr"] = {number: tuple(semantic_review(record) for record in records) for number, records in args["reviews_by_pr"].items()}
    args["checks_by_pr"] = {number: tuple(semantic_check(record) for record in records) for number, records in args["checks_by_pr"].items()}
    a, b = (derive_positions(**args), derive_positions(**args))
    assert a == b
    assert [i.number for i in a.issues] == [7]
    assert a.prs[0].verdict == 'pass' and a.prs[0].checks == 'green'
    assert a.prs[0].contributor is False
    assert a.train.version == '1.2.3' and a.train.next_version == '1.2.4'
    assert list(tmp_path.iterdir()) == []
_FORM_BODY = '### Summary\n\nThe link 404s.\n\n### Complexity\n\nHigh\n\n### Priority\n\nHighest\n'

@intent('INT-FC-R93')
def test_complexity_and_priority_are_read_from_the_issue_body_marker():
    assert read_ticket_signal(_FORM_BODY, 'Complexity', ('low', 'medium', 'high')) == 'high'
    assert read_ticket_signal(_FORM_BODY, 'Priority', ('lowest', 'low', 'medium', 'high', 'highest')) == 'highest'
    assert read_ticket_signal('Complexity: Medium', 'Complexity', ('low', 'medium', 'high')) == 'medium'
    assert read_ticket_signal('complexity: LOW', 'Complexity', ('low', 'medium', 'high')) == 'low'
    assert read_ticket_signal('no marker here', 'Complexity', ('low', 'medium', 'high')) == ''
    assert read_ticket_signal('### Complexity\n\n_No response_\n', 'Complexity', ('low', 'medium', 'high')) == ''
    assert read_ticket_signal('Complexity: gigantic', 'Complexity', ('low', 'medium', 'high')) == ''
    assert read_ticket_signal(None, 'Complexity', ('low', 'medium', 'high')) == ''
    assert read_ticket_signal('the Priority: high stuff is inline', 'Priority', ('high',)) == ''
    assert read_ticket_signal('intro\nPriority: high\nmore', 'Priority', ('high',)) == 'high'
    issue = {**_issue(7, 'broken link'), 'body': _FORM_BODY}
    pos = derive_positions('org/app', tuple(semantic_issue(record) for record in ([issue])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])
    assert (pos.issues[0].complexity, pos.issues[0].priority) == ('high', 'highest')
    plain = derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(9, 'no marker')])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])
    assert (plain.issues[0].complexity, plain.issues[0].priority) == ('', '')

@intent('INT-FC-R94')
def test_native_issue_type_is_read_straight_from_the_payload():
    typed = {**_issue(3, 'crash on load'), 'type': {'name': 'Bug'}}
    pos = derive_positions('org/app', tuple(semantic_issue(record) for record in ([typed])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])
    assert pos.issues[0].type == 'Bug'
    for shape in ({}, {'type': None}, {'type': {}}):
        issue = {**_issue(4, 'untyped'), **shape}
        assert derive_positions('org/app', tuple(semantic_issue(record) for record in ([issue])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], []).issues[0].type == ''

@intent('INT-FC-R59')
def test_release_train_computes_what_the_pipeline_would_cut():
    assert latest_version(['v1.2.3', 'v1.10.0', 'chart-x']) == '1.10.0'
    t = derive_train(['v2.5.0'], ['fix: a', 'feat: b', 'docs: c'])
    assert (t.fix, t.feat, t.other, t.unreleased_total) == (1, 1, 1, 3)
    assert t.next_version == '2.6.0'
    assert derive_train(['v2.5.0'], ['feat!: breaking']).next_version == '3.0.0'
    assert derive_train(['v2.5.0'], ['fix: only']).next_version == '2.5.1'
    assert derive_train(['v2.5.0'], ['docs: d', 'ci: e']).next_version == ''
    assert derive_train(['v2.5.0'], []).next_version == ''
    assert derive_train([], ['feat: no tag yet']).next_version == ''
_VERDICT_TABLE = json.loads((Path(__file__).resolve().parents[1] / 'orchestrator' / 'vendor' / 'fixtures' / 'verdict' / 'verdict-reader.json').read_text(encoding='utf-8'))

def _as_rest(review: dict, at: str) -> dict:
    """A review in the reader's fields, as the REST API hands it to the console."""
    return {'user': {'login': (review.get('author') or {}).get('login') or ''}, 'body': review.get('body') or '', 'author_association': review.get('authorAssociation') or '', 'state': review.get('state') or '', 'submitted_at': at}

@intent('INT-FC-R66')
@pytest.mark.parametrize('case', _VERDICT_TABLE['cases'], ids=lambda c: c['name'])
def test_the_verdict_is_the_playbooks_table_read_through_the_adapter(case):
    given, expected = (case['input'], case['expected'])
    reviews = [_as_rest(r, f'2026-07-10T00:{i:02d}:00Z') for i, r in enumerate(given['reviews'])]
    verdict, findings = decide(tuple(semantic_review(record) for record in reversed(reviews)), given['author'], given['merger'])
    assert verdict == expected['verdict']
    decided = expected['decided_by']
    assert findings == ('' if decided is None else given['reviews'][decided].get('body') or '')

@intent('INT-FC-R66')
def test_the_adapter_reads_logins_caselessly_and_hands_back_the_deciding_findings():
    fail = _review('Fc-Review', 'missing test\nVERDICT: FAIL')
    assert decide(tuple(semantic_review(record) for record in ([fail])), 'fc-git') == ('fail', 'missing test\nVERDICT: FAIL')
    assert derive_verdict(tuple(semantic_review(record) for record in ([_review('FC-GIT', 'VERDICT: PASS')])), 'fc-git') == 'unrecorded'
    assert derive_verdict(tuple(semantic_review(record) for record in ([_review('fc-console', 'VERDICT: PASS')])), 'fc-git', 'FC-Console') == 'unrecorded'
    assert derive_verdict(tuple(semantic_review(record) for record in ([_review('fc-console', 'VERDICT: PASS')])), 'fc-git') == 'pass'
    assert decide(tuple(semantic_review(record) for record in ([])), 'fc-git') == ('awaiting', '')

@intent('INT-FC-R66')
def test_an_unrecorded_review_reaches_the_queue_as_awaiting_an_independent_reviewer():
    green = [semantic_check({'status': 'completed', 'conclusion': 'success'})]
    reviewed = [_review('fc-git', 'No findings.\n\nVERDICT: UNRECORDED')]
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'feat(#7): calendar', head='feat/7-calendar'), _pr(13, 'chore: tidy', head='chore/tidy')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: reviewed, 13: reviewed}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: green, 13: green}).items()}, [], [], git_user='fc-git')]
    assert [p.verdict for p in pos[0].prs] == ['unrecorded', 'unrecorded']
    items = derive_inbox(pos)
    ticket = next((it for it in items if it.number == 7))
    assert ticket.stage == 'awaiting-review' and ticket.act == 'review'
    tidy = next((it for it in items if it.number == 13))
    assert (tidy.signal, tidy.act) == ('pr-review', 'review')
    assert tidy.detail == 'PR #13 awaits an independent reviewer: chore: tidy'

@intent('INT-FC-R91')
def test_agent_identities_reviewer_distinct_from_author():
    ours = {'foundry-delivery', 'foundry-review'}
    assert derive_verdict(tuple(semantic_review(record) for record in ([_review('foundry-review', 'fresh eyes\nVERDICT: PASS')])), 'foundry-delivery') == 'pass'
    assert derive_verdict(tuple(semantic_review(record) for record in ([_review('carlos', 'VERDICT: PASS')])), 'foundry-delivery') == 'pass'
    assert is_contributor('foundry-delivery', ours) is False
    assert is_contributor('carlos', ours) is True

@intent('INT-FC-R64')
def test_mode_from_request_is_validated_and_never_rewritten():
    assert parse_mode(None) is MaintenanceMode.GATED
    assert parse_mode('') is MaintenanceMode.GATED
    assert parse_mode('one-shot') is MaintenanceMode.ONE_SHOT
    assert parse_mode('direct') is MaintenanceMode.DIRECT
    with pytest.raises(ValueError):
        parse_mode('yolo')
    assert not hasattr(maintenance_modes, 'effective_mode')
    assert is_contributor('colleague', 'fc-git') is True
    assert is_contributor('fc-git', 'fc-git') is False

def test_checks_state_folds_fail_closed():
    assert checks_state(tuple(semantic_check(record) for record in ([]))) == 'unknown'
    assert checks_state(tuple(semantic_check(record) for record in ([{'status': 'completed', 'conclusion': 'success'}]))) == 'green'
    assert checks_state(tuple(semantic_check(record) for record in ([{'status': 'completed', 'conclusion': 'success'}, {'status': 'completed', 'conclusion': 'failure'}]))) == 'red'
    assert checks_state(tuple(semantic_check(record) for record in ([{'status': 'in_progress', 'conclusion': None}]))) == 'pending'

def test_one_shot_merge_gate_is_total_and_fail_closed():
    assert judge_one_shot('pass', 'green') is MergeGate.MERGE
    for verdict, checks in [('pass', 'red'), ('pass', 'pending'), ('pass', 'unknown'), ('fail', 'green'), ('unrecorded', 'green'), ('awaiting', 'green'), ('', '')]:
        assert judge_one_shot(verdict, checks) is MergeGate.PARK

@intent('INT-FC-R75')
def test_resolve_fail_retries_within_budget_then_degrades():
    assert MAX_RESOLVE_ATTEMPTS == 2
    assert judge_resolve_fail(1) is ResolveRetry.RETRY
    assert judge_resolve_fail(2) is ResolveRetry.DEGRADE
    assert judge_resolve_fail(3) is ResolveRetry.DEGRADE
    assert judge_resolve_fail(4) is ResolveRetry.DEGRADE
    assert judge_resolve_fail(1, max_attempts=1) is ResolveRetry.DEGRADE

@intent('INT-FC-R68')
def test_inbox_derives_the_org_queue_and_never_surfaces_archived():
    pos = [MaintenancePositions(repo='org/app', issues=(), prs=(), train=ReleaseTrain(version='1.0.0', unreleased_total=2, fix=2, next_version='1.0.1')), derive_positions('org/tool', tuple(semantic_issue(record) for record in ([_issue(3, 'drift')])), tuple(semantic_pr(record) for record in ([_pr(4, 'fix: x (#3)')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({4: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({4: [{'status': 'completed', 'conclusion': 'failure'}]}).items()}, [], [], git_user='fc-git'), MaintenancePositions(repo='org/archived-thing', issues=derive_positions('org/archived-thing', tuple(semantic_issue(record) for record in ([_issue(1, 'ghost')])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], []).issues[0:1])]
    items = derive_inbox(pos, archived={'org/archived-thing'})
    repos = [it.repo for it in items]
    assert 'org/archived-thing' not in repos
    assert items[0].signal == 'red-ci' and items[0].repo == 'org/tool'
    signals = [it.signal for it in items]
    assert signals.index('red-ci') < signals.index('unreleased') < signals.index('issue')
    assert all((it.act for it in items))
    red_main = derive_positions('org/shipper', tuple(semantic_issue(record) for record in ([])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, ['v1.6.0'], [], default_checks=tuple(semantic_check(record) for record in ([{'status': 'completed', 'conclusion': 'failure'}])))
    assert red_main.train.checks == 'red'
    only = derive_inbox([red_main])
    assert [it.signal for it in only] == ['red-ci']
    assert only[0].act == 'investigate' and '1.6.0' in only[0].detail
    mixed = derive_inbox([derive_positions('org/other', tuple(semantic_issue(record) for record in ([])), tuple(semantic_pr(record) for record in ([_pr(4, 'feat: y (#3)')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({4: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({4: []}).items()}, [], []), red_main])
    assert mixed[0].signal == 'red-ci' and mixed[0].repo == 'org/shipper'
    for state in ([{'status': 'completed', 'conclusion': 'success'}], []):
        quiet = derive_positions('org/fine', tuple(semantic_issue(record) for record in ([])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, ['v1.0.0'], [], default_checks=tuple(semantic_check(record) for record in (state)))
        assert derive_inbox([quiet]) == []

@intent('INT-FC-R82')
def test_inbox_surfaces_a_running_maintenance_run_and_folds_its_issue():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar'), _issue(9, 'other')])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])]
    items = derive_inbox(pos, running={'org/app': [{'act': 'resolve', 'ticket': 7}]})
    assert items[0].signal == 'running' and items[0].number == 7
    assert 'in progress' in items[0].detail and 'calendar' in items[0].detail
    assert not any((it.signal == 'issue' and it.number == 7 for it in items))
    assert any((it.signal == 'issue' and it.number == 9 for it in items))

@intent('INT-FC-R82')
def test_inbox_running_is_empty_without_the_executor():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'x')])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])]
    assert not any((it.signal == 'running' for it in derive_inbox(pos)))

@intent('INT-FC-R97')
def test_inbox_folds_a_resolving_prs_row_into_its_open_issue_row():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(10, 'dup signal'), _issue(9, 'other')])), tuple(semantic_pr(record) for record in ([_pr(20, 'fix(#10): dup signal', head='fix/10-dup-signal'), _pr(21, 'chore: unrelated', head='chore/21-unrelated')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({20: [], 21: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({20: [{'status': 'completed', 'conclusion': 'failure'}], 21: []}).items()}, [], [])]
    items = derive_inbox(pos)
    signals = {(it.signal, it.number) for it in items}
    assert ('issue', 10) in signals
    assert ('red-ci', 20) not in signals
    assert ('pr-review', 20) not in signals
    assert ('pr-review', 21) in signals
    assert ('issue', 9) in signals

@intent('INT-FC-R97')
def test_inbox_resolving_pr_match_also_reads_the_ticket_reference_from_the_body():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(10, 'dup signal')])), tuple(semantic_pr(record) for record in ([_pr(20, 'fix: dup signal', head='fix/10-dup-signal', body='Closes #10')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({20: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({20: []}).items()}, [], [])]
    items = derive_inbox(pos)
    signals = {(it.signal, it.number) for it in items}
    assert ('issue', 10) in signals
    assert ('pr-review', 20) not in signals

@intent('INT-FC-R59')
def test_deployment_health_reads_only_an_explicit_unhealthy_word_as_unhealthy():
    assert deployment_health('running') is True
    assert deployment_health('paused') is None
    for absent in ('', 'unknown', 'pending', 'progressing', '  ', None):
        assert deployment_health(absent) is None
    for broken in ('error', 'failed', 'degraded', 'unhealthy', 'crashloopbackoff', 'CrashLoopBackOff'):
        assert deployment_health(broken) is False

@intent('INT-FC-R68')
def test_inbox_drift_fires_on_a_genuinely_unhealthy_deployment():
    pos = [MaintenancePositions(repo='org/app', train=ReleaseTrain(version='1.0.0', deployed='running', healthy=False))]
    items = derive_inbox(pos)
    drift = [it for it in items if it.signal == 'drift']
    assert len(drift) == 1
    assert drift[0].repo == 'org/app' and drift[0].act == 'investigate'
    for healthy in (True, None):
        healthy_pos = [MaintenancePositions(repo='org/app', train=ReleaseTrain(healthy=healthy))]
        assert not any((it.signal == 'drift' for it in derive_inbox(healthy_pos)))

@intent('INT-FC-R96')
def test_inbox_marks_foundry_hidden_tickets_but_keeps_them_in_the_derivation():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'noise-free wontfix', labels=('foundry-hidden',)), _issue(9, 'plain ticket')])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])]
    items = derive_inbox(pos)
    by_number = {it.number: it for it in items if it.signal == 'issue'}
    assert by_number[7].hidden is True
    assert by_number[9].hidden is False
    assert all((it.hidden is False for it in items if it.signal != 'issue'))

@intent('INT-FC-R98')
def test_inbox_folds_the_issue_row_for_any_running_act_not_resolve_only():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'feat(#7): calendar', head='feat/7-calendar')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: []}).items()}, [], [])]
    items = derive_inbox(pos, running={'org/app': [{'act': 'review', 'ticket': 12}]})
    assert items[0].signal == 'running' and items[0].number == 7 and (items[0].stage == 'in-progress')
    assert items[0].detail == 'review PR #12 for #7 in progress: add calendar'
    assert not any((it.signal == 'issue' and it.number == 7 for it in items))
    assert not any((it.signal in ('pr-review', 'red-ci') for it in items))
    assert [it.number for it in items] == [7]

@intent('INT-FC-R98')
def test_inbox_running_review_of_a_pr_that_resolves_nothing_keeps_its_own_concern():
    pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'chore: bump deps', head='chore/bump-deps')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: []}).items()}, [], [])]
    items = derive_inbox(pos, running={'org/app': [{'act': 'review', 'ticket': 12}]})
    assert items[0].signal == 'running' and items[0].number is None
    assert items[0].detail == 'review PR #12 in progress'
    assert not any((it.signal == 'pr-review' for it in items))
    assert any((it.signal == 'issue' and it.number == 7 for it in items))

@intent('INT-FC-R98')
def test_inbox_issue_stage_reflects_its_linked_open_pr():
    open_pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [])]
    open_item = next((it for it in derive_inbox(open_pos) if it.number == 7))
    assert open_item.stage == 'open' and open_item.act == 'resolve'
    gate_pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'feat(#7): calendar', head='feat/7-calendar')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: []}).items()}, [], [])]
    gate_item = next((it for it in derive_inbox(gate_pos) if it.number == 7))
    assert gate_item.stage == 'awaiting-review' and gate_item.act == 'review'
    merge_pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'feat(#7): calendar', head='feat/7-calendar')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: [_review('fc-review', 'solid\n\nVERDICT: PASS')]}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: [{'status': 'completed', 'conclusion': 'success'}]}).items()}, [], [], git_user='fc-git')]
    merge_item = next((it for it in derive_inbox(merge_pos) if it.number == 7))
    assert merge_item.stage == 'awaiting-merge' and merge_item.act == 'merge'
    red_pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'feat(#7): calendar', head='feat/7-calendar')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: [_review('fc-review', 'solid\n\nVERDICT: PASS')]}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: [{'status': 'completed', 'conclusion': 'failure'}]}).items()}, [], [], git_user='fc-git')]
    red_item = next((it for it in derive_inbox(red_pos) if it.number == 7))
    assert red_item.stage == 'checks-red' and red_item.act == 'investigate'
    fail_pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'feat(#7): calendar', head='feat/7-calendar')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: [_review('fc-review', 'not yet\n\nVERDICT: FAIL')]}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: [{'status': 'completed', 'conclusion': 'success'}]}).items()}, [], [], git_user='fc-git')]
    fail_item = next((it for it in derive_inbox(fail_pos) if it.number == 7))
    assert fail_item.stage == 'changes-requested' and fail_item.act == 'resolve'
    coincidence_pos = [derive_positions('org/app', tuple(semantic_issue(record) for record in ([_issue(7, 'add calendar')])), tuple(semantic_pr(record) for record in ([_pr(12, 'release 7 rc', head='release/7-rc')])), {number: tuple(semantic_review(record) for record in records) for number, records in ({12: []}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({12: []}).items()}, [], [])]
    coincidence_item = next((it for it in derive_inbox(coincidence_pos) if it.number == 7))
    assert coincidence_item.stage == 'open'

@intent('INT-FC-R84')
def test_pr_resolves_ticket_is_branch_and_text():
    from orchestrator.application.maintenance_resolver import pr_resolves_ticket
    assert pr_resolves_ticket('feat/7-calendar', 'feat(#7): calendar', 'Closes #7', 7)
    assert pr_resolves_ticket('fix/7-x', 'fix: x', 'Closes #7', 7)
    assert not pr_resolves_ticket('release/7-rc', 'release 7 rc', 'cutting the rc', 7)
    assert not pr_resolves_ticket('some/other-branch', 'feat: x', 'mentions #7', 7)
    assert not pr_resolves_ticket('feat/77-x', 'feat(#77): y', 'Closes #77', 7)

@intent('INT-FC-R83')
def test_positions_expose_recent_closed_prs_by_state():
    pos = derive_positions('org/app', tuple(semantic_issue(record) for record in ([])), tuple(semantic_pr(record) for record in ([])), {number: tuple(semantic_review(record) for record in records) for number, records in ({}).items()}, {number: tuple(semantic_check(record) for record in records) for number, records in ({}).items()}, [], [], closed_prs=tuple(semantic_pr(record) for record in ([{'number': 14, 'title': 'feat(#7): calendar', 'head': {'ref': 'feat/7-calendar-page'}, 'merged_at': '2026-07-13T14:40:00Z', 'html_url': 'http://x/pull/14'}, {'number': 12, 'title': 'fix(#5): x', 'head': {'ref': 'fix/5-x'}, 'merged_at': None, 'html_url': 'http://x/pull/12'}])))
    by_num = {p.number: p for p in pos.recent_closed}
    assert by_num[14].state == 'merged'
    assert by_num[12].state == 'closed'
    assert all((p.state == 'open' for p in pos.prs))

@intent('INT-FC-R100')
def test_delivery_prompt_from_comments_reads_the_latest_marked_comment():
    comments = [{'body': 'a plain human comment, no marker'}, {'body': f'{DELIVERY_PROMPT_MARKER}\nFirst pass: build the reporting module.'}, {'body': 'another human note in between'}, {'body': f'{DELIVERY_PROMPT_MARKER}\n\nBuild the reporting module: dashboards, exports, schedules.\n'}]
    assert delivery_prompt_from_comments(tuple(semantic_comment(record) for record in (comments))) == 'Build the reporting module: dashboards, exports, schedules.'
    assert delivery_prompt_from_comments(tuple(semantic_comment(record) for record in ([{'body': 'no marker here'}]))) == ''
    assert delivery_prompt_from_comments(tuple(semantic_comment(record) for record in ([]))) == ''
    assert delivery_prompt_from_comments(None) == ''

@intent('INT-FC-R100')
def test_delivery_prompt_of_falls_back_to_the_ticket_body():
    marked = [{'body': f'{DELIVERY_PROMPT_MARKER}\nBuild the reporting module.'}]
    assert delivery_prompt_of(tuple(semantic_comment(record) for record in (marked)), 'the raw ask') == 'Build the reporting module.'
    assert delivery_prompt_of(tuple(semantic_comment(record) for record in ([{'body': DELIVERY_PROMPT_MARKER}])), 'the body') == 'the body'
    assert delivery_prompt_of(tuple(semantic_comment(record) for record in ([{'body': 'no marker'}])), '\n## Line 4: reports\n\nBuild it.\n') == '## Line 4: reports\n\nBuild it.'
    assert delivery_prompt_of(tuple(semantic_comment(record) for record in ([])), None) == ''
    assert delivery_prompt_of(None, '   ') == ''
_INBOX_FIXTURES = sorted((Path(__file__).resolve().parents[1] / 'orchestrator' / 'vendor' / 'fixtures').glob('*.json'))

def _positions_from(case: dict) -> tuple[list[MaintenancePositions], set[str], dict]:
    """A fixture case expressed in the CONSOLE's own vocabulary.

    The corpus can mark a position archived inline; this repo says the same thing with the
    `archived` set, because its scan drops those repos before a position is ever built. Both
    reach the derivation, so translating here is honest - it is the console asking the same
    question in its own words, which is exactly what the adapter is for.
    """
    positions, archived = ([], set(case['input'].get('archived') or []))
    for pos in case['input']['positions']:
        if pos.get('archived'):
            archived.add(pos['repo'])
        positions.append(MaintenancePositions(repo=pos['repo'], issues=tuple((IssuePosition(number=i['number'], title=i.get('title', ''), author='', labels=tuple(i.get('labels') or []), created_at=i.get('created_at', '')) for i in pos.get('issues') or [])), prs=tuple((PrPosition(number=p['number'], title=p.get('title', ''), author='', head=p.get('head', ''), body=p.get('body', ''), verdict=p.get('verdict', VERDICT_AWAITING), checks=p.get('checks', CHECKS_UNKNOWN), updated_at=p.get('updated_at', '')) for p in pos.get('prs') or [])), train=ReleaseTrain(version=(pos.get('train') or {}).get('version') or '', unreleased_total=(pos.get('train') or {}).get('unreleased_total') or 0, next_version=(pos.get('train') or {}).get('next_version') or '', deployed=(pos.get('train') or {}).get('deployed') or '', healthy=(pos.get('train') or {}).get('healthy'), checks=(pos.get('train') or {}).get('checks') or CHECKS_UNKNOWN)))
    running: dict[str, list[dict]] = {}
    for job in case['input'].get('running') or []:
        running.setdefault(job['repo'], []).append({'act': job['act'], 'ticket': job['number']})
    promotion = {pos['repo']: pos['promotion'] for pos in case['input']['positions'] if pos.get('promotion')}
    hidden_repos = {r for r in case['input'].get('hidden_repos') or []}
    return (positions, archived, running, promotion, hidden_repos)

@pytest.mark.parametrize('path', _INBOX_FIXTURES, ids=lambda p: p.stem)
@intent('INT-FC-R122')
def test_the_console_queue_matches_the_playbook_corpus(path):
    """Every corpus case, run through THIS repo's adapter rather than the pure derivation.

    Re-running the vendored sweep alone would prove nothing the playbook's own suite does
    not already prove about the same bytes. What is new here is the mapping - typed
    positions in, InboxItems out - so that is what the corpus is pointed at: a field the
    adapter drops (a PR body, a train's health, a label) shows up as a row that disagrees
    with the corpus instead of as a queue that is quietly less correct than the contract.
    """
    case = json.loads(path.read_text(encoding='utf-8'))
    positions, archived, running, promotion, hidden_repos = _positions_from(case)
    got = derive_inbox(positions, archived=archived, running=running, promotion=promotion, hidden_repos=hidden_repos)
    assert [asdict(item) for item in got] == case['expected'], case['why']

@intent('INT-FC-R122')
def test_the_rules_live_in_the_playbook_and_this_module_only_adapts():
    """The architectural half of the claim, asserted rather than hoped for.

    A queue rule re-typed here is invisible until it disagrees with another reader in
    production, which is precisely the failure this landing removes. So the module is held
    to being an adapter: it reads the vendored sweep, and it does not restate the
    vocabulary - the urgency order, the stage names, the link rule - in its own words.
    """
    source = (Path(__file__).resolve().parents[1] / 'orchestrator' / 'application' / 'fleet_inbox.py').read_text(encoding='utf-8')
    assert 'from orchestrator.vendor import sweep' in source
    assert 'sweep.derive_inbox(' in source
    for restated in ('"red-ci"', '"pr-review"', '"unreleased"', '"drift"', '"awaiting-merge"', '"changes-requested"', '"awaiting-review"', '"checks-red"', '"in-progress"', 'URGENCY'):
        assert restated not in source, f"fleet_inbox.py names {restated}: the queue's vocabulary belongs to the playbook sweep, and a copy here is a second source of truth"
