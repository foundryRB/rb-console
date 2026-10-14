"""A line command selects its runs by repository identity, which GitHub resolves
case-insensitively: the command's context lowercases it, while an execution's annotation
keeps the case it was created with (INT-FC-R180). In a mixed-case organisation an exact
comparison matched nothing, so a drive never stopped an older run, a sign never released
the parked run, and a close left the line's runs behind."""
from execution_fixtures import run_rows
from pytest_intent import intent

from orchestrator.application.services.delivery.release_parked_run import helper_release_parked_run
from orchestrator.application.services.runs.line_runs import helper_line_runs
from orchestrator.application.services.runs.supersede_runs import helper_supersede_runs
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata

ANNOTATED = "Owner-Org/App"
COMMANDED = "owner-org/app"
SCRATCH = "delivery/2026-10-08"


class Workflows:
    def __init__(self):
        self.stopped: list[str] = []
        self.resumed: list[str] = []

    def list_runs(self):
        return run_rows([
            {"name": "d-old", "handle": "h-old", "phase": "Running"},
            {"name": "d-park", "handle": "h-park", "phase": "Suspended", "parked_gate": "proposal"},
            {"name": "d-other", "handle": "h-other", "phase": "Running"},
        ])

    def metadata_of(self, handle):
        repository = "Owner-Org/Other" if handle == "h-other" else ANNOTATED
        return WorkflowMetadata(repository, "v1", handle, "delivery", SCRATCH)

    def stop(self, handle, *, reason, expected_version):
        self.stopped.append(handle)

    def resume(self, handle, *, expected_version):
        self.resumed.append(handle)


@intent("INT-FC-R180")
def test_the_lines_runs_are_selected_whatever_the_case_of_the_identity():
    assert [row.handle for row in helper_line_runs(COMMANDED, workflows=Workflows())] == ["h-old", "h-park"]


@intent("INT-FC-R180")
def test_a_drive_stops_the_lines_older_runs_and_no_other_lines():
    wf = Workflows()
    helper_supersede_runs(COMMANDED, workflows=wf)
    assert wf.stopped == ["h-old", "h-park"]


@intent("INT-FC-R180")
def test_a_sign_releases_the_run_parked_on_its_gate():
    wf = Workflows()
    helper_release_parked_run(COMMANDED, "proposal", workflows=wf, scratch_ref=SCRATCH)
    assert wf.resumed == ["h-park"]
    assert "h-other" not in wf.stopped
