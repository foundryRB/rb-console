"""Read semantic execution retention from the operator's setting."""

from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.domain.model.run_retention import RunRetention


def helper_retention_gc(*, cap_run_retention: RunRetentionPort) -> RunRetention:
    return RunRetention(**cap_run_retention.execute())
