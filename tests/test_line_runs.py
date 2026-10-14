from capability_support import with_lifecycle
from execution_fixtures import execution_graph, run_rows
from delivery_fixtures import record_inputs
"""A line's runs end WITH the line: a close deletes them beside the scratch it removes, and
a fresh establish over a name whose previous line never closed deletes what that line left.

The console reads a line's runs off the repo's name, so anything left behind is adopted by the
next line under that name. On 2026-09-11 a demo retired without a close (a demo is retired,
never closed, so nothing stopped its runs) had its repo deleted and re-established under the
same name; the run still parked on the old line's design gate was read as the new line's, and
the cockpit sat on a gate that line could never sign."""
from capability_support import command_kwargs
from pytest_intent import intent
from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle, lifecycle_digest
from orchestrator.domain.services.delivery_resolution import derive_from_records
from capability_support import make_capabilities

def _row(name, phase='Succeeded'):
    return {'name': name, 'handle': f'live:workflow.argoproj.io/{name}', 'phase': phase}

class _Workflows:

    def __init__(self, rows):
        self._rows = list(rows)
        self.stopped = []
        self.deleted = []
        self.repository = "acme"

    def list_runs(self):
        return run_rows([r for r in self._rows if r['handle'] not in self.deleted])

    def stop(self, handle, terminate=False, reason='', *, expected_version=None):
        self.stopped.append(handle)
        return 'Stop'

    def metadata_of(self, handle):
        from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
        return WorkflowMetadata("other" if "delivery-other-" in handle else self.repository, "v1", handle, "delivery", "")

    def graph(self, handle):
        return execution_graph({"phase": "Stopped"})

    def logs(self, handle):
        return "retained logs"

    def delete(self, handle, *, expected_version, expected_uid):
        self.deleted.append(handle)
        return 'deleted'

class _Repos:
    """A repo holding a delivery, whose close the service delegates to."""

    def __init__(self, contents=None):
        self.contents = contents if contents is not None else {'proposal.md': 'gate: proposal\nsigned: 2026-09-12\n'}
        self.closed = []
        self.registered = []

    def list_delivery_repos(self):
        return []

    def close_line(self, repo, *, expected_revision=''):
        self.closed.append(repo)

    def ensure(self, target):
        return f'org/{target}'

    def register(self, workspace, request='', source=(), source_name=''):
        self.registered.append(workspace)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class _Source:

    def __init__(self, repos, exists=True):
        self._repos = repos
        self._exists = exists

    def read_config(self, repo, *, revision=""):
        from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE, CURRENT_PLAYBOOK_REF
        return {"lifecycle": {**encode_lifecycle(CURRENT_LIFECYCLE), "source_ref": CURRENT_PLAYBOOK_REF, "digest": lifecycle_digest(CURRENT_LIFECYCLE)}}

    def state_of(self, repo):
        return derive_from_records(repo, self._exists, record_inputs(dict(self._repos.contents)))

@intent('INT-FC-R157')
def test_close_ends_the_lines_runs_with_it():
    """Close stops what is live and then deletes every run of the line - another delivery's
    runs untouched - so the name carries none of them afterwards."""
    repos = _Repos()
    wf = _Workflows([_row('delivery-acme-new', 'Suspended'), _row('delivery-acme-old'), _row('delivery-other-x', 'Suspended')])
    svc = make_capabilities(repos, source=_Source(repos), workflows=wf)
    svc.close_line.execute('acme', **command_kwargs('acme'))
    assert repos.closed == ['acme']
    assert wf.stopped == ['live:workflow.argoproj.io/delivery-acme-new']
    assert wf.deleted == ['live:workflow.argoproj.io/delivery-acme-new', 'live:workflow.argoproj.io/delivery-acme-old']

@intent('INT-FC-R157')
def test_establish_inherits_no_run_from_a_line_that_never_closed():
    """A name freed by a retirement, a crash, or a deleted repo can still carry the previous
    line's runs. The line minted here inherits none: the parked one is stopped and both go."""
    repos = _Repos(contents={})
    wf = _Workflows([_row('delivery-acme-parked', 'Suspended'), _row('delivery-acme-done')])
    wf.repository = 'org/acme'
    svc = make_capabilities(repos, workflows=wf, source=_Source(repos, exists=False))
    svc.establish.execute('acme', 'Build it', **command_kwargs('acme'))
    assert repos.registered == ['org/acme']
    assert wf.stopped == ['live:workflow.argoproj.io/delivery-acme-parked']
    assert wf.deleted == ['live:workflow.argoproj.io/delivery-acme-parked', 'live:workflow.argoproj.io/delivery-acme-done']

@intent('INT-FC-R157')
def test_establish_over_a_repo_that_already_holds_a_line_ends_nothing():
    """Establish also adopts: a repo whose line is open and working is re-established for a
    recast, and its runs are that line's own. Only a repo holding no line is swept."""
    repos = _Repos()
    wf = _Workflows([_row('delivery-acme-live', 'Running')])
    svc = make_capabilities(repos, source=_Source(repos), workflows=wf)
    svc.establish.execute('acme', 'Recast it', **command_kwargs('acme'))
    assert wf.stopped == [] and wf.deleted == []
