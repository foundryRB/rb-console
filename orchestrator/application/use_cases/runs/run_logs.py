"""RunLogs over consumed application contracts."""
from __future__ import annotations

from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.services.run_history import filter_node_lines


class RunLogs:

    def __init__(self, *, run_log_store: RunLogStore | None, workflows: WorkflowRunner | None) -> None:
        self.run_log_store = run_log_store
        self.workflows = workflows

    def execute(self, handle: str, tail: int=400, node_id: str | None=None) -> str:
        """The run's step logs: the live executor read first, the completed run's snapshot
        once its pods are GC'd (INT-FC-R108). node_id scopes either source to one node's
        pod (INT-FC-R109) - the band's inspector reads one step, not the whole run. Empty
        when available. Executor unavailability requires a retained snapshot."""
        if self.workflows is None or not handle:
            return ''
        unavailable = None
        try:
            text = self.workflows.logs(handle, tail, node_id) if node_id else self.workflows.logs(handle, tail)
        except SourceUnavailable as exc:
            unavailable = exc
            text = ''
        if text:
            return text
        if self.run_log_store is None:
            if unavailable is not None:
                raise unavailable
            return text
        snapshot = self.run_log_store.load(handle.rsplit('/', 1)[-1])
        if snapshot is None:
            if unavailable is not None:
                raise unavailable
            return ''
        return filter_node_lines(snapshot, node_id) if node_id else snapshot
