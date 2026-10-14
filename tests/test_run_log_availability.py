"""A retained log satisfies reads through an unavailable executor."""
import pytest
from pytest_intent import intent

from orchestrator.application.use_cases.runs.run_logs import RunLogs
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


class Executor:
    def logs(self, handle, tail):
        raise SourceUnavailable("executor unavailable")

class Archive:
    def __init__(self, snapshot):
        self.snapshot = snapshot
    def load(self, name):
        return self.snapshot

@pytest.mark.parametrize("archive", [None, Archive(None)])
def test_unavailable_executor_without_retained_log_is_visible(archive):
    with pytest.raises(SourceUnavailable, match="executor unavailable"):
        RunLogs(workflows=Executor(), run_log_store=archive).execute("ns/run")

@intent('INT-FC-R108')
def test_retained_log_satisfies_an_unavailable_executor():
    assert RunLogs(workflows=Executor(), run_log_store=Archive("retained log")).execute("ns/run") == "retained log"

def test_empty_unconfigured_executor_is_supported():
    assert RunLogs(workflows=None, run_log_store=None).execute("ns/run") == ""
