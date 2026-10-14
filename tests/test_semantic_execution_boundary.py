"""Executor wire data is decoded before core inventory, graphs, or archives see it."""

import json
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest
from pytest_intent import intent

from orchestrator.adapters.inbound.http.mappers.execution import graph_dto, run_dto
from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
from orchestrator.adapters.outbound.argo.argo_workflow_runner import (
    ArgoWorkflowRunner,
    parse_graph,
    parse_runs,
)
from orchestrator.adapters.outbound.memory.observation_store import (
    MemoryObservationStore,
)
from orchestrator.application.use_cases.runs.run_graph import RunGraph
from orchestrator.application.use_cases.runs.runs import Runs
from orchestrator.domain.exceptions.retained_evidence_unreadable import (
    RetainedEvidenceUnreadable,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.retained_execution import RetainedExecution
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def executor_object():
    return {
        "metadata": {
            "name": "run-1",
            "resourceVersion": "17",
            "annotations": {
                "foundry-console/repository": "owner/app",
                "foundry-console/delegated-grant": '{"grant_id":"opaque"}',
            },
            "labels": {
                "foundry-console/run": "run-1",
                "foundry-console/maintenance": "resolve",
                "foundry-console/ticket": "42",
            },
        },
        "status": {
            "phase": "Failed",
            "nodes": {
                "n": {
                    "id": "n",
                    "displayName": "resolve",
                    "type": "Pod",
                    "phase": "Failed",
                    "startedAt": "2026-10-05T09:00:00Z",
                    "outputs": {"exitCode": "65"},
                }
            },
        },
    }


@intent("INT-FC-R163")
def test_actual_executor_normalizes_semantic_fields_before_core(monkeypatch):
    wire = executor_object()
    monkeypatch.setenv("FC_DRIVE_LIVE", "1")
    monkeypatch.setattr(
        "orchestrator.adapters.outbound.argo.argo_workflow_runner.subprocess.run",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"items": [wire]} if "-l" in argv else wire)
        ),
    )
    runner = ArgoWorkflowRunner()
    row = runner.list_runs()[0]
    graph = runner.graph(row.handle)
    assert isinstance(row, RunInventoryEntry) and isinstance(graph, ExecutionGraph)
    assert (row.repository, row.kind, row.ticket, row.grant_id) == (
        "owner/app",
        "maintenance",
        42,
        "opaque",
    )
    assert graph.nodes[0].kind == "worker" and graph.nodes[0].exit_code == 65
    assert graph.nodes[0].started_at == "2026-10-05T09:00:00Z"
    assert not hasattr(row, "get") and not hasattr(graph.nodes[0], "exitCode")
    with pytest.raises(FrozenInstanceError):
        row.repository = "other/app"
    assert run_dto(row)["ticket"] == "42" and "grant_id" not in run_dto(row)
    assert graph_dto(graph)["nodes"][0]["exitCode"] == "65"


@intent("INT-FC-R164")
def test_typed_archive_survives_restart_and_projection_reads_do_not_observe(tmp_path):
    wire = executor_object()
    row, graph = parse_runs({"items": [wire]})[0], parse_graph(wire)
    FileRunLogStore(str(tmp_path)).save_metadata(
        row.name, RetainedExecution(row, graph)
    )
    retained = FileRunLogStore(str(tmp_path)).all_metadata()[0]
    assert retained == RetainedExecution(row, graph)
    observations = MemoryObservationStore()
    observations.runs = [retained.run]
    observations.graphs[row.handle] = retained.graph
    assert Runs(observations=observations).execute() == [row]
    assert RunGraph(observations=observations).execute(row.handle) == graph
    assert RunGraph(observations=observations).execute("unobserved").nodes == ()


@pytest.mark.parametrize("damage", ["item", "nodes", "outputs", "exit", "children", "artifact-name", "overall-phase"])
def test_malformed_executor_evidence_is_typed_unavailable(damage):
    wire = executor_object()
    if damage == "item":
        with pytest.raises(SourceUnavailable):
            parse_runs({"items": [None]})
        return
    if damage == "nodes":
        wire["status"]["nodes"] = []
    elif damage == "outputs":
        wire["status"]["nodes"]["n"]["outputs"] = "invalid"
    elif damage == "exit":
        wire["status"]["nodes"]["n"]["outputs"]["exitCode"] = "unproven"
    elif damage == "artifact-name":
        wire["status"]["nodes"]["n"]["outputs"]["artifacts"] = [{"name": 17}]
    elif damage == "overall-phase":
        wire["status"]["phase"] = 17
    else:
        wire["status"]["nodes"]["n"]["children"] = [None]
    with pytest.raises(SourceUnavailable):
        parse_graph(wire)


def test_malformed_archive_cannot_be_published_as_empty_inventory(tmp_path):
    (tmp_path / "run.log.json").write_text(
        '{"row": {"name": "old-wire-record"}}', encoding="utf-8"
    )
    with pytest.raises(SourceUnavailable):
        FileRunLogStore(str(tmp_path)).all_metadata()


def _archived(tmp_path):
    """A store holding one retained run, its record's path, and the run itself."""
    wire = executor_object()
    retained = RetainedExecution(parse_runs({"items": [wire]})[0], parse_graph(wire))
    store = FileRunLogStore(str(tmp_path))
    store.save_metadata(retained.run.name, retained)
    return store, tmp_path / f"{retained.run.name}.log.json", retained


@intent("INT-FC-R194")
def test_a_record_written_before_a_defaulted_field_reads_as_its_default(tmp_path):
    store, path, retained = _archived(tmp_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    for node in record["graph"]["nodes"]:
        del node["refusal"]
    del record["run"]["agents"]
    path.write_text(json.dumps(record), encoding="utf-8")
    expected = RetainedExecution(
        replace(retained.run, agents=()),
        replace(
            retained.graph,
            nodes=tuple(replace(node, refusal=None) for node in retained.graph.nodes),
        ),
    )
    assert store.all_metadata() == [expected]


@intent("INT-FC-R194")
@pytest.mark.parametrize(
    "damage", ["unknown-record-key", "unknown-node-key", "missing-required-field"]
)
def test_an_unknown_key_or_a_missing_required_field_is_still_malformed(tmp_path, damage):
    store, path, _ = _archived(tmp_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    if damage == "unknown-record-key":
        record["verdict"] = "pass"
    elif damage == "unknown-node-key":
        record["graph"]["nodes"][0]["verdict"] = "pass"
    else:
        del record["run"]["handle"]
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(SourceUnavailable):
        store.all_metadata()


@intent("INT-FC-R194")
def test_an_unreadable_record_withholds_only_itself(tmp_path):
    store, _, retained = _archived(tmp_path)
    (tmp_path / "broken.log.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RetainedEvidenceUnreadable) as refused:
        store.all_metadata()
    assert refused.value.unreadable == ("broken.log.json",)
    assert refused.value.retained == (retained,)


@intent("INT-FC-R194")
def test_the_tick_merges_the_records_it_read_and_reports_the_archive_unavailable(tmp_path):
    from capability_support import make_capabilities

    class Repositories:
        def list_delivery_repos(self):
            return []

    class ExecutorPastTheRun:
        def list_runs(self):
            return []

        def graph(self, handle):
            raise SourceUnavailable("no such workflow")

        def logs(self, handle, tail):
            raise SourceUnavailable("no such workflow")

    store, _, retained = _archived(tmp_path)
    service = make_capabilities(
        Repositories(), workflows=ExecutorPastTheRun(), run_log_store=store
    )
    assert service.refresh.execute() >= 0
    (tmp_path / "broken.log.json").write_text("{not json", encoding="utf-8")
    assert service.refresh.execute() == -1
    assert service.runs.execute() == [retained.run]
    assert service.run_graph.execute(retained.run.handle) == retained.graph
    freshness = service.snapshot_metadata.execute()["freshness"]
    assert freshness["reason_code"] == "source_unavailable"


@intent("INT-FC-R82")
def test_executor_outage_retains_typed_runs_and_marks_the_projection_stale():
    from capability_support import make_capabilities

    class Repositories:
        def list_delivery_repos(self):
            return []

    class UnavailableExecutor:
        def list_runs(self):
            raise SourceUnavailable("executor unavailable")

        def graph(self, handle):
            raise SourceUnavailable("executor unavailable")

        def logs(self, handle, tail):
            raise SourceUnavailable("executor unavailable")

    service = make_capabilities(Repositories(), workflows=UnavailableExecutor())
    prior = parse_runs({"items": [executor_object()]})[0]
    observations = service.refresh.observations
    observations.runs = [prior]
    observations.metadata[""] = {"freshness": {"observed_at": "2026-10-05T08:00:00Z"}}
    assert service.refresh.execute() == -1
    assert service.runs.execute() == [prior]
    freshness = service.snapshot_metadata.execute()["freshness"]
    assert (
        freshness["state"] == "stale"
        and freshness["reason_code"] == "source_unavailable"
    )
    assert freshness["observed_at"] == "2026-10-05T08:00:00Z"
