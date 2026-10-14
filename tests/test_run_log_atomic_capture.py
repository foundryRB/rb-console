"""Only a complete durable capture publishes a run archive marker."""

from execution_fixtures import run_row

import tempfile
from types import SimpleNamespace

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
from orchestrator.application.services.runs.snapshot_terminal_runs import (
    helper_snapshot_terminal_runs,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


@pytest.mark.parametrize("prior", [None, "retained previous capture"])
@intent("INT-FC-R108")
def test_interrupted_write_preserves_final_capture_and_restart_can_retry(
    monkeypatch, tmp_path, prior
):
    archive = FileRunLogStore(str(tmp_path))
    if prior is not None:
        archive.save("run", prior)
    create = tempfile.NamedTemporaryFile

    def interrupted(*args, **kwargs):
        stream = create(*args, **kwargs)
        write = stream.write

        def partial_write(text):
            write(text[:4])
            stream.flush()
            raise OSError("capture write interrupted")

        stream.write = partial_write
        return stream

    with monkeypatch.context() as fault:
        fault.setattr(tempfile, "NamedTemporaryFile", interrupted)
        with pytest.raises(SourceUnavailable):
            archive.save("run", "complete captured evidence")
    restarted = FileRunLogStore(str(tmp_path))
    assert restarted.has("run") is (prior is not None)
    assert restarted.load("run") == prior
    assert list(tmp_path.glob("*.pending")) == []
    if prior is None:
        reads = []
        helper_snapshot_terminal_runs(
            [run_row({"name": "run", "handle": "live/run", "phase": "Succeeded"})],
            run_log_store=restarted,
            workflows=SimpleNamespace(
                logs=lambda *args: reads.append(args) or "complete captured evidence"
            ),
            cap_run_retention=SimpleNamespace(execute=lambda: {"ttl_failure_days": 7}),
        )
        assert len(reads) == 1
        assert restarted.load("run") == "complete captured evidence"
    else:
        restarted.save("run", "complete captured evidence")
        assert restarted.load("run") == "complete captured evidence"


def test_abandoned_pending_file_is_not_a_confirmed_capture(tmp_path):
    (tmp_path / ".capture-interrupted.pending").write_text("partial", encoding="utf-8")
    store = FileRunLogStore(str(tmp_path))
    assert not store.has("run")
    assert store.load("run") is None
    assert store.all_metadata() == []
    store.save("run", "")
    assert store.has("run")
    assert store.load("run") == ""
