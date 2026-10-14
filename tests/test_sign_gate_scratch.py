"""The cockpit Sign hands the gate helper a faithful scratch, and keeps what it wrote.

``GitHubRepoStore.write_gate`` runs the playbook's stamper against a scratch it
synthesizes in a temp dir rather than a clone. That shim was partial in both directions
and the gap was invisible while the vendored pin lagged six commits behind the playbook:

  - it seeded only the record, so the stamper's journal precondition (REF-Delivery
    section 1, anti-pattern 38) read every line as journal-less and refused every Sign;
  - it wrote back only the record, so the gate export - the artifact-creation moment that
    freezes the phase tool's deliverables into the scratch before the signature lands
    (Phases and Artifacts, principle 02) - produced files that died with the temp dir.

These pin both directions. The first pair runs the REAL vendored helper, so a future pin
bump that adds another precondition fails here rather than at a live gate.
"""
import base64
from dataclasses import replace
import json
import re
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
import pytest
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from pytest_intent import intent
from orchestrator.adapters.outbound.github import github_repo_store as github_store
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.adapters.outbound.records.yaml_record_parser import parse
from orchestrator.domain.model.record_status import RecordStatus
_VENDORED = Path(__file__).resolve().parents[1] / 'devops' / 'vendor' / 'stamp_gate.py'
_VENDORED_REACH = Path(__file__).resolve().parents[1] / 'devops' / 'vendor' / 'reach_gate.py'
_REF = 'delivery/2026-08-18'

def _use_helper(monkeypatch, path: Path) -> None:
    """Point the store at a helper. ``FC_STAMP_HELPER`` is read once at import (the pod
    sets it before the process starts), so a test swaps the resolved module attribute."""
    monkeypatch.setattr(github_store, '_STAMP_HELPER', str(path))
_RECORD = '---\nphase: design\nskill: design-session\nstatus: gate\ngate: design\nsigned: pending\nreviewed: 2026-08-09\nrun: r1\nattempt: 1\nmode: interactive\nstarted: 2026-08-09T00:00:00Z\nfinished:\ncredential_ref: x\n---\n\nPrototype: none - the tool-less design path; nothing external for the gate to freeze.\n\n# Design\n'

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

class RecordedWrites(list):

    def __init__(self) -> None:
        super().__init__()
        self.commits = []
        self.ref_updates = []

def _wire(monkeypatch, files: dict[str, str], refs: list[str] | None=None):
    """Serve immutable scratch reads and commit all changed files in one ref update."""
    sent = RecordedWrites()
    namespace = [_REF] if refs is None else refs
    tip = f'tip-{_REF}'
    pending = []

    def urlopen(req, timeout=0):
        nonlocal tip, pending
        method = req.get_method()
        path = req.full_url.replace('https://api.github.com', '')
        if method == 'GET' and path.endswith('/git/matching-refs/heads/delivery/'):
            return _Resp([{'ref': f'refs/heads/{r}', 'object': {'sha': tip if r == _REF else f'tip-{r}'}} for r in namespace])
        if method == 'GET' and '/git/commits/' in path:
            assert path.endswith(tip)
            return _Resp({'tree': {'sha': 'base-tree'}})
        rel = path.split('/contents/', 1)[1] if '/contents/' in path else ''
        rel, _, query = rel.partition('?')
        if method == 'GET':
            assert any((f"ref={quote(ref, safe='')}" in query for ref in (_REF, tip))), f'scratch read must use its ref or immutable tip: {path}'
            if rel not in files:
                raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
            return _Resp({'content': base64.b64encode(files[rel].encode()).decode(), 'sha': f'sha-{rel}'})
        body = json.loads(req.data.decode())
        if method == 'POST' and path.endswith('/git/trees'):
            assert body['base_tree'] == 'base-tree'
            pending = body['tree']
            return _Resp({'sha': 'new-tree'})
        if method == 'POST' and path.endswith('/git/commits'):
            assert body['parents'] == [tip]
            sent.commits.append(body)
            return _Resp({'sha': 'new-commit'})
        if method == 'PATCH' and path.endswith(f'/git/refs/heads/{_REF}'):
            assert body == {'sha': 'new-commit', 'force': False}
            sent.ref_updates.append(body)
            for entry in pending:
                sent.append((entry['path'], entry['content']))
                files[entry['path']] = entry['content']
            tip = 'new-commit'
            return _Resp({})
        assert method == 'PUT' and body.get('branch') == _REF, f'scratch write must name the ref: {path}'
        text = base64.b64decode(body['content']).decode()
        sent.append((rel, text))
        files[rel] = text
        return _Resp({})
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: urlopen(request, timeout))
    return sent

def _store() -> GitHubRepoStore:
    return GitHubRepoStore('Example-Org-Of-Engineering', lambda: 't0ken')

@pytest.fixture(autouse=True)
def _use_vendored_helper(monkeypatch):
    """Both helper paths resolve to the vendored pin, for the same reason: the store reads
    each one once at import, and the acts under test run the REAL helper the image bakes."""
    _use_helper(monkeypatch, _VENDORED)
    monkeypatch.setattr(github_store, '_REACH_HELPER', str(_VENDORED_REACH))

@intent('INT-FC-R52')
def test_sign_seeds_the_journal_so_the_real_helper_can_close_the_gate(monkeypatch):
    """The regression: the shim never fetched journal.md, so the stamper's journal
    precondition refused every console Sign."""
    sent = _wire(monkeypatch, {'design.md': _RECORD, 'journal.md': '# Journal\n\nentries\n'})
    _store().write_gate('racer-v0', 'design.md', '2026-08-09', definition=CURRENT_LIFECYCLE)
    written = dict(sent)
    assert 'design.md' in written
    assert 'signed: 2026-08-09' in written['design.md']
    assert 'status: complete' in written['design.md']
    assert 'journal.md' not in written

@intent('INT-FC-R52')
def test_sign_surfaces_the_helper_refusal_when_the_line_has_no_journal(monkeypatch):
    """Absent upstream is a real state the helper is entitled to refuse on. The shim must
    NOT invent a journal to get past the check - that would forge the evidence the check
    exists to demand - so the refusal reaches the cockpit verbatim."""
    sent = _wire(monkeypatch, {'design.md': _RECORD})
    with pytest.raises(ValueError) as err:
        _store().write_gate('racer-v0', 'design.md', '2026-08-09', definition=CURRENT_LIFECYCLE)
    assert 'journal.md' in str(err.value)
    assert sent == [], 'a refused stamp writes nothing'

@intent('INT-FC-R52')
def test_sign_commits_gate_exports_and_signature_atomically(monkeypatch, tmp_path):
    """A proposal or design stamp exports the phase tool's deliverables into the scratch
    before signing. Those must reach the repo; a Sign that returned only the record threw
    them away. Driven by a stub helper so the assertion is about the store, not about a
    reachable prototype instance."""
    stub = tmp_path / 'stub_stamp.py'
    stub.write_text("import sys, pathlib\nrepo = pathlib.Path(sys.argv[sys.argv.index('--repo') + 1])\nscratch = repo / '.delivery'\n(scratch / 'design' / 'screens').mkdir(parents=True, exist_ok=True)\n(scratch / 'design' / 'theme.css').write_text(':root{--primary:22 90% 55%;}', encoding='utf-8')\n(scratch / 'design' / 'screens' / 'home.html').write_text('<main>home</main>', encoding='utf-8')\nrecord = scratch / 'design.md'\nrecord.write_text(record.read_text(encoding='utf-8').replace('signed: pending', 'signed: 2026-08-09'), encoding='utf-8')\n", encoding='utf-8')
    _use_helper(monkeypatch, stub)
    sent = _wire(monkeypatch, {'design.md': _RECORD, 'journal.md': '# Journal\n\nentries\n'})
    _store().write_gate('racer-v0', 'design.md', '2026-08-09', definition=CURRENT_LIFECYCLE)
    paths = [p for p, _ in sent]
    assert 'design/theme.css' in paths
    assert 'design/screens/home.html' in paths
    assert len(sent.commits) == 1
    assert len(sent.ref_updates) == 1
    assert paths.count('design.md') == 1
    assert 'signed: 2026-08-09' in dict(sent)['design.md']

@intent('INT-FC-R52')
def test_a_helper_that_reports_success_without_stamping_is_not_written_back(monkeypatch, tmp_path):
    """Success plus an untouched record is incoherent; committing it would publish an
    unsigned record under a `sign gate` commit message."""
    stub = tmp_path / 'noop_stamp.py'
    stub.write_text('import sys\n', encoding='utf-8')
    _use_helper(monkeypatch, stub)
    sent = _wire(monkeypatch, {'design.md': _RECORD, 'journal.md': '# Journal\n\nentries\n'})
    with pytest.raises(ValueError, match='unstamped'):
        _store().write_gate('racer-v0', 'design.md', '2026-08-09', definition=CURRENT_LIFECYCLE)
    assert sent == []

@intent('INT-FC-R52')
def test_sign_surfaces_a_ref_resolution_failure_as_its_own_error(monkeypatch):
    """The scratch ref is resolved BEFORE anything is fetched, and a repo that carries
    none (or more than one) refuses with the resolution named. A silently-empty
    resolution would read as an empty scratch and surface as the stamper's
    journal-absent refusal - a misleading message for a line whose journal sits right
    on its ref - so the distinct error is the difference between 'fix your refs' and
    'go write a journal'."""
    for namespace, why in (([], 'no delivery/'), ([_REF, 'delivery/2026-08-01'], 'more than one')):
        sent = _wire(monkeypatch, {'design.md': _RECORD, 'journal.md': 'j\n'}, refs=namespace)
        with pytest.raises(ValueError) as err:
            _store().write_gate('racer-v0', 'design.md', '2026-08-09', definition=CURRENT_LIFECYCLE)
        assert why in str(err.value)
        assert 'journal' not in str(err.value)
        assert sent == []
_SIGNED = _RECORD.replace('signed: pending', 'signed: 2026-08-09')

@intent('INT-FC-R39')
def test_write_config_rides_the_line_ref(monkeypatch):
    """The mode persists to the scratch's config.json ON the line's ref: the
    existence probe follows ?ref= and the PUT names branch:, both asserted by the
    harness on every call (a config landing on the default branch would resurrect
    the scratch there)."""
    sent = _wire(monkeypatch, {'config.json': '{"mode": "interactive"}\n'})
    _store().write_config('racer-v0', {'mode': 'one-shot'})
    written = dict(sent)
    assert set(written) == {'config.json'}
    assert '"mode": "one-shot"' in written['config.json']

@intent('INT-FC-R39')
def test_a_save_that_changes_nothing_commits_nothing(monkeypatch):
    """Re-saving the mode a line already carries makes no empty commit, so the line's
    revision - which every later command is checked against - stays where the operator
    last read it (playbook#477: two empty "set mode" commits failed the next Sign)."""
    sent = _wire(monkeypatch, {'config.json': json.dumps({'mode': 'interactive'}, indent=2) + '\n'})
    _store().write_config('racer-v0', {'mode': 'interactive'})
    assert list(sent) == [] and sent.commits == []
    _store().write_config('racer-v0', {'mode': 'one-shot'})
    assert '"mode": "one-shot"' in dict(sent)['config.json']

@intent('INT-FC-R70')
def test_append_journal_rides_the_line_ref(monkeypatch):
    """The re-drive's feedback journals to journal.md at the ref's branch root - read
    off the ref (?ref=), written back naming it (branch:) - so the durable-before-live
    record lands on the scratch, never the default branch."""
    sent = _wire(monkeypatch, {'journal.md': '# Journal\n\nentries\n'})
    _store().append_journal('racer-v0', '## proposal gate: re-driven\n\nreprice REQ-3')
    written = dict(sent)
    assert set(written) == {'journal.md'}
    assert 'entries' in written['journal.md'] and 'reprice REQ-3' in written['journal.md']

@intent('INT-FC-R40')
def test_reopen_gate_rides_the_line_ref(monkeypatch):
    """Un-signing reads the record off the ref and writes the re-opened form back onto it
    (branch: named), leaving every other scratch file untouched."""
    sent = _wire(monkeypatch, {'design.md': _SIGNED, 'journal.md': '# J\n'})
    _store().reopen_gate('racer-v0', 'design.md')
    written = dict(sent)
    assert set(written) == {'design.md'}
    assert 'signed: pending' in written['design.md']
_CLOSED = "---\nphase: intent+plan\nskill: intent-session\nstatus: complete\ngate: plan\nsigned: 2026-08-24\nreviewed: 2026-08-24\nrun: r1\nattempt: 1\nmode: one-shot\nstarted: 2026-08-24T09:00:00Z\nfinished: 2026-08-24T17:00:00Z\ncredential_ref: fc-run-abc123\nonboarding_pr: https://github.com/acme/platform/pull/7\nattests: 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b\n---\n\n# Build handoff\n\nAttempt 1's plan.\n"

@intent('INT-FC-R40')
def test_reopen_runs_the_record_helper_and_clears_the_previous_attempt(monkeypatch):
    """The live defect (#77, ai-assessment delivery/2026-08-11): the console re-opened a
    gate by replacing the stamped date with PENDING and nothing else, so the record it
    handed back still read `status: complete` and still carried the PREVIOUS attempt's
    `reviewed:` date. stamp_gate.py takes a dated `reviewed:` as sufficient evidence and
    signs without a verdict, so the ordinary stamp command then closed the NEW attempt's
    gate over the OLD attempt's review, with no guard refusing.

    Against the REAL vendored helper, so a pin bump that changes which fields a re-open
    clears fails here rather than at a live gate."""
    sent = _wire(monkeypatch, {'handoff.md': _CLOSED, 'journal.md': '# J\n'})
    _store().reopen_gate('racer-v0', 'handoff.md')
    written = dict(sent)
    assert set(written) == {'handoff.md'}
    front = parse(written['handoff.md'])
    assert front.signed is False and front.status == RecordStatus.IN_PROGRESS
    assert front.reviewed is False
    assert 'attests:' not in written['handoff.md']
    assert re.search('^finished:\\s*$', written['handoff.md'], re.MULTILINE)
    assert front.run == 'r1' and front.attempt == 1 and (front.mode == 'one-shot')
    assert front.phase == 'intent+plan' and front.skill == 'intent-session' and (front.gate == 'plan')
    assert 'started: 2026-08-24T09:00:00Z' in written['handoff.md']
    assert 'onboarding_pr: https://github.com/acme/platform/pull/7' in written['handoff.md']
    assert "Attempt 1's plan." in written['handoff.md']

@intent('INT-FC-R52')
def test_the_vendored_pin_carries_the_gate_export(monkeypatch):
    """The pin lagged six commits and the baked stamper had no exporters at all, so pods
    never ran the gate export. Assert the machinery is present in what ships."""
    source = _VENDORED.read_text(encoding='utf-8')
    assert '_export_estimation' in source and '_export_prototype' in source
_PROPOSAL = '---\nphase: scope\nskill: deliver-engagement\nstatus: gate\ngate: proposal\nsigned: pending\nreviewed: 2026-08-12\nrun: r1\nattempt: 1\nmode: interactive\nstarted: 2026-08-11T15:13:13Z\nfinished:\ncredential_ref: x\ndelivers: P1\n---\n\n# Proposal\n'
_ARCH = '@startuml\ncomponent [console]\n@enduml\n'
_ASSUMPTIONS = 'Assumption ID\tAssumption\nA1\tThe instance is reachable\n'
_PROJECT = 'ID\tStream\tActivity\tEffort (MD)\nA1\tBuild Activities\tbuild\t10\nA2\tProject Management\tsteer\t2.5\n'

@pytest.fixture
def estimation_instance():
    """A stub estimation instance on a real socket. The helper runs in a SUBPROCESS, so a
    monkeypatched urlopen cannot reach it - only a real door can. Records the slugs asked
    for, which is how the test pins whose project was exported."""
    asked: list[str] = []

    class Handler(BaseHTTPRequestHandler):

        def do_GET(self):
            path = self.path.split('/api/projects/', 1)[-1]
            slug, _, rest = path.partition('/')
            asked.append(slug)
            if rest == 'files':
                body = {'files': [{'name': 'P1-overview.puml', 'path': 'data/architecture/P1-overview.puml'}, {'name': 'P2-overview.puml', 'path': 'data/architecture/P2-overview.puml'}, {'name': '02-assumptions.tsv', 'path': 'data/assumptions/02-assumptions.tsv'}, {'name': 'P1-build.tsv', 'path': 'data/activities/P1-build.tsv'}, {'name': 'P1-project.tsv', 'path': 'data/activities/P1-project.tsv'}]}
            elif rest.startswith('files/'):
                src = rest[len('files/'):]
                if 'assumption' in src:
                    content = _ASSUMPTIONS
                elif src.endswith('P1-project.tsv'):
                    content = _PROJECT
                else:
                    content = _ARCH
                body = {'content': content}
            else:
                self.send_error(404)
                return
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield (f'http://127.0.0.1:{server.server_port}', asked)
    server.shutdown()
    server.server_close()

@intent('INT-FC-R120')
def test_sign_hands_the_real_helper_the_instance_to_export_the_proposal_from(monkeypatch, estimation_instance):
    """The regression: a proposal stamp exports the delivered phase's architecture and
    assumptions BEFORE signing, and the helper is handed no instance to export from - it
    looks in ESTIMATEKIT_BASE_URL, which belongs to a workstation - so every console Sign
    of a proposal gate died on `REFUSED: no estimation instance to export from`. Drives
    the REAL vendored helper against a real door, because that refusal is exactly what a
    stub helper cannot reproduce."""
    base, _asked = estimation_instance
    monkeypatch.setattr(github_store, 'internal_base_url', lambda studio, svc='': base)
    sent = _wire(monkeypatch, {'proposal.md': _PROPOSAL, 'journal.md': '# Journal\n\nentries\n'})
    _store().write_gate('ai-assessment', 'proposal.md', '2026-08-13', definition=CURRENT_LIFECYCLE)
    written = dict(sent)
    assert 'architecture/P1-overview.puml' in written
    assert 'architecture/P2-overview.puml' not in written
    assert 'assumptions/02-assumptions.tsv' in written
    assert written['architecture/P1-overview.puml'] == _ARCH
    assert written['estimate/P1-project.tsv'] == _PROJECT
    assert 'estimate/P1-build.tsv' in written
    assert [p for p, _ in sent][-1] == 'proposal.md'
    record = written['proposal.md']
    assert 'signed: 2026-08-13' in record
    assert '| Build Activities | 10 MD |' in record and '| Total | 12.5 MD |' in record
    assert re.search('^signed_at: \\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$', record, re.MULTILINE)
    assert 'outcome: as it stood' in record


@intent('INT-FC-R120', 'INT-FC-R167')
def test_renamed_proposal_record_exports_through_the_captured_definition(monkeypatch, estimation_instance):
    base, asked = estimation_instance
    studios = []
    def studio_url(studio, svc=''):
        studios.append(studio)
        return base
    monkeypatch.setattr(github_store, 'internal_base_url', studio_url)
    initial = CURRENT_LIFECYCLE
    phases = list(initial.phases)
    phases[0] = replace(phases[0], name='discovery', record='brief.md', gate='proposal-review')
    phases[1] = replace(phases[1], inputs=('discovery',))
    definition = replace(initial, version='1.1.0', phases=tuple(phases))
    body = _PROPOSAL.replace('phase: scope', 'phase: discovery').replace('gate: proposal', 'gate: proposal-review')
    sent = _wire(monkeypatch, {'brief.md': body, 'journal.md': '# Journal\n\nentries\n'})
    _store().write_gate('ai-assessment', 'brief.md', '2026-08-13', definition=definition)
    written = dict(sent)
    assert studios == ['estimatekit']
    assert asked and set(asked) == {'ai-assessment'}
    assert written['architecture/P1-overview.puml'] == _ARCH
    assert 'signed: 2026-08-13' in written['brief.md']
    assert len(sent.commits) == len(sent.ref_updates) == 1

@intent('INT-FC-R120')
def test_the_exported_project_is_the_delivery_not_the_temp_directory(monkeypatch, estimation_instance):
    """The helper reads the estimation slug off the repo folder NAME (one repo, one
    estimation project, named for it - REF-Delivery section 1). The scratch is synthesized
    in a temp dir, so that resolved to a random temp name - a project no instance holds -
    until the synthesized root was named for the delivery. That naming is now the only
    thing that picks the export's project: the helper's `## Estimation project` prose
    scrape has been removed, having read a record's instance URL as a project name and
    refused a live gate."""
    base, asked = estimation_instance
    monkeypatch.setattr(github_store, 'internal_base_url', lambda studio, svc='': base)
    _wire(monkeypatch, {'proposal.md': _PROPOSAL, 'journal.md': '# Journal\n\nentries\n'})
    _store().write_gate('Example-Org-Of-Engineering/ai-assessment', 'proposal.md', '2026-08-13', definition=CURRENT_LIFECYCLE)
    assert asked and set(asked) == {'ai-assessment'}

@intent('INT-FC-R120')
def test_each_gated_record_is_pointed_at_its_own_phase_tool(monkeypatch, tmp_path):
    """proposal exports from the estimation instance and design from the prototype one;
    the records that register no exporter (handoff, build) are pointed at nothing. Pinned
    on the argv, so the mapping cannot drift into sending a design gate to estimatekit."""
    argv_log = tmp_path / 'argv.json'
    stub = tmp_path / 'argv_stamp.py'
    stub.write_text(f"import json, sys, pathlib\npathlib.Path({str(argv_log)!r}).write_text(json.dumps(sys.argv), encoding='utf-8')\nrepo = pathlib.Path(sys.argv[sys.argv.index('--repo') + 1])\nrecord = repo / '.delivery' / sys.argv[sys.argv.index('--record') + 1]\nrecord.write_text(record.read_text(encoding='utf-8').replace('signed: pending', 'signed: 2026-08-13'), encoding='utf-8')\n", encoding='utf-8')
    _use_helper(monkeypatch, stub)
    monkeypatch.setattr(github_store, 'internal_base_url', lambda studio, svc='': f'http://{studio}.internal')

    def tool_url_for(record: str, body: str) -> str | None:
        _wire(monkeypatch, {record: body, 'journal.md': '# Journal\n\nentries\n'})
        _store().write_gate('ai-assessment', record, '2026-08-13', definition=CURRENT_LIFECYCLE)
        argv = json.loads(argv_log.read_text(encoding='utf-8'))
        return argv[argv.index('--tool-url') + 1] if '--tool-url' in argv else None
    assert tool_url_for('proposal.md', _PROPOSAL) == 'http://estimatekit.internal'
    assert tool_url_for('design.md', _RECORD) == 'http://protopane.internal'
    assert tool_url_for('handoff.md', _PROPOSAL.replace('gate: proposal', 'gate: plan')) is None
