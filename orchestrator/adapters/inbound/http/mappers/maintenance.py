"""Semantic maintenance command results rendered for HTTP."""

from orchestrator.domain.model.maintenance_drive_result import MaintenanceDriveResult


def maintenance_drive_response(result: MaintenanceDriveResult) -> dict[str, str]:
    return {
        "run_id": result.run_id,
        "handle": result.handle,
        "act": result.act,
        "mode": result.mode.value,
    }
