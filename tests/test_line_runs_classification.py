"""A line command's scan of the executor's inventory classifies only executions that can
still act (INT-FC-R175). The scan behind a drive's supersede, a sign's release, and a
close's or establish's end-runs is one helper, so this is where the rule is checked."""
from execution_fixtures import run_rows
import pytest
from pytest_intent import intent

from orchestrator.application.services.runs.line_runs import helper_line_runs
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata

REPO = "owner/app"


class Workflows:
    """An inventory holding one execution the console cannot classify (`h-legacy`: no
    captured coordinates, the shape every pre-6.18 console wrote) beside a live parked run
    of the line and a live run of another line."""

    def __init__(self, legacy_phase):
        self.asked: list[str] = []
        self._legacy_phase = legacy_phase

    def list_runs(self):
        return run_rows([
            {"name": "delivery-app-legacy", "handle": "h-legacy", "phase": self._legacy_phase},
            {"name": "delivery-app-park", "handle": "h-park", "phase": "Suspended"},
            {"name": "delivery-other-live", "handle": "h-other", "phase": "Running"},
            {"name": "delivery-app-done", "handle": "h-done", "phase": "Succeeded"},
        ])

    def metadata_of(self, handle):
        self.asked.append(handle)
        if handle == "h-legacy":
            raise Conflict("The workflow execution kind is unavailable or invalid.")
        return WorkflowMetadata("other/app" if handle == "h-other" else REPO, "v1", handle, "delivery", "")


@intent("INT-FC-R175")
@pytest.mark.parametrize("phase", ["Succeeded", "Failed", "Error", "Stopped"])
def test_a_finished_execution_the_console_cannot_classify_is_passed_over(phase):
    wf = Workflows(phase)
    selected = helper_line_runs(REPO, workflows=wf)
    # The line's own runs, live and finished alike (a close deletes the finished ones,
    # INT-FC-R157); the one the console cannot place is passed over, not raised.
    assert [row.handle for row in selected] == ["h-park", "h-done"]


@intent("INT-FC-R175")
@pytest.mark.parametrize("phase", ["Running", "Pending", "Suspended", "Stopping"])
def test_a_live_execution_whose_kind_cannot_be_read_still_refuses(phase):
    """The fail-closed read stays for a live execution: the scan would stop or resume it,
    and must not act on one it cannot place."""
    with pytest.raises(Conflict):
        helper_line_runs(REPO, workflows=Workflows(phase))
