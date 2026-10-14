from execution_fixtures import run_rows
from delivery_fixtures import record_inputs
"""The delivery index serves reads from a cache and refreshes from a source out of
band, so a page load never triggers a scan."""
from capability_support import command_kwargs
from pytest_intent import intent
from orchestrator.adapters.outbound.memory.index import DeliveryIndex
from orchestrator.domain.services.delivery_resolution import derive_from_records

class FakeSource:

    def __init__(self, states):
        self._states = states
        self.scans = 0

    def scan(self):
        self.scans += 1
        return self._states

@intent('INT-FC-R30')
def test_index_serves_from_cache_and_refreshes_out_of_band():
    scope = derive_from_records('acme', True, record_inputs({}))
    idx = DeliveryIndex()
    src = FakeSource([scope])
    assert idx.all() == []
    assert idx.scanned is False
    assert src.scans == 0
    assert idx.refresh(src) == 1
    assert src.scans == 1
    assert idx.scanned is True
    assert idx.get('acme').status == 'run-phase'
    assert [s.repo for s in idx.all()] == ['acme']
    assert src.scans == 1

def test_put_writes_one_delivery_through():
    """put() closes the act-to-rescan gap: one fresh entry lands without a scan."""
    idx = DeliveryIndex()
    idx.refresh(FakeSource([derive_from_records('acme', True, record_inputs({}))]))
    fresh = derive_from_records('acme', True, record_inputs({'proposal.md': 'signed: 2026-07-11'}))
    idx.put(fresh)
    assert idx.get('acme') is fresh
    assert [s.repo for s in idx.all()] == ['acme']

def test_sign_writes_through_to_the_index():
    """Signing a gate updates the warm cache in the same act (read-your-write): the next
    cached read agrees with the signature instead of un-signing it until the rescan."""
    from capability_support import make_capabilities

    class Repos:

        def __init__(self):
            self.contents = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n'}

        def write_gate(self, repo, record, date, *, definition, expected_revision=''):
            self.contents[record] = f'---\nstatus: complete\ngate: proposal\nsigned: {date}\nreviewed: 2026-01-01\n---\n'

    class Source:

        def __init__(self, repos):
            self._repos = repos

        def state_of(self, repo):
            return derive_from_records(repo, True, record_inputs(dict(self._repos.contents)))

        def scan(self):
            return [self.state_of('acme')]
    repos = Repos()
    src = Source(repos)
    idx = DeliveryIndex()
    idx.refresh(src)
    svc = make_capabilities(repos, index=idx, source=src)
    assert not svc.status.execute('acme').gates[0].signed
    fresh = svc.sign_gate.execute('acme', **command_kwargs('acme'))
    assert fresh.gates[0].signed
    assert svc.status.execute('acme').gates[0].signed

def _sign_service(rows):
    """A delivery awaiting its proposal gate, with the executor holding ``rows``."""
    from capability_support import make_capabilities

    class Repos:

        def __init__(self):
            self.contents = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n'}

        def write_gate(self, repo, record, date, *, definition, expected_revision=''):
            self.contents[record] = f'---\nstatus: complete\ngate: proposal\nsigned: {date}\nreviewed: 2026-01-01\n---\n'

    class Source:

        def __init__(self, repos):
            self._repos = repos

        def state_of(self, repo):
            return derive_from_records(repo, True, record_inputs(dict(self._repos.contents)))

    class Workflows:

        def __init__(self):
            self.resumed = []
            self.stopped = []

        def list_runs(self):
            return run_rows(rows)

        def metadata_of(self, handle):
            from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
            return WorkflowMetadata("other" if "delivery-other-" in handle else "acme", "v1", handle, "delivery", "")

        def resume(self, handle, *, expected_version=None):
            self.resumed.append(handle)
            return 'resumed:1'

        def stop(self, handle, terminate=False, reason='', *, expected_version=None):
            self.stopped.append(handle)
            return 'Stop'
    repos = Repos()
    wf = Workflows()
    return (make_capabilities(repos, source=Source(repos), workflows=wf), wf)

def _parked(name, gate):
    return {'name': name, 'handle': f'live:workflow.argoproj.io/{name}', 'phase': 'Suspended', 'parked_gate': gate}

@intent('INT-FC-R156')
def test_sign_releases_the_run_parked_on_the_gate_it_signed():
    """Signing resumes the run waiting on THAT gate (the gate card's 'releases the next
    phase' promise) and supersedes the line's other parked runs, newest first. Another
    delivery's run is not this sign's to touch."""
    svc, wf = _sign_service([_parked('delivery-acme-new', 'proposal'), _parked('delivery-acme-old', 'proposal'), _parked('delivery-other-x', 'proposal')])
    svc.sign_gate.execute('acme', **command_kwargs('acme'))
    assert wf.resumed == ['live:workflow.argoproj.io/delivery-acme-new']
    assert wf.stopped == ['live:workflow.argoproj.io/delivery-acme-old']

@intent('INT-FC-R156')
def test_sign_stops_a_run_parked_on_a_gate_the_line_has_passed():
    """A line driven on at a terminal leaves the console's run parked on an earlier gate.
    Released, its next step would re-run a phase the line already holds, two workers then
    sharing one scratch ref; left alone, it holds the cockpit's primary disabled on a gate
    nobody can sign. So the sign stops it, and the primary falls back to the next drive."""
    svc, wf = _sign_service([_parked('delivery-acme-design', 'design')])
    svc.sign_gate.execute('acme', **command_kwargs('acme'))
    assert wf.resumed == []
    assert wf.stopped == ['live:workflow.argoproj.io/delivery-acme-design']
