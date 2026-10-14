"""Compile and parse a delivery execution for browser regression fixtures."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from orchestrator.adapters.outbound.argo.argo_workflow_compiler import (
    ArgoWorkflowCompiler,
)
from orchestrator.adapters.outbound.argo.argo_workflow_runner import parse_runs
from orchestrator.adapters.inbound.http.mappers.execution import run_dto
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.target_kind import TargetKind

repo, run_id, phase = sys.argv[1:4]
kind = sys.argv[4] if len(sys.argv) > 4 else "delivery"
compiler = ArgoWorkflowCompiler()
config = RunConfig("secret", repo, True)
if kind == "delivery":
    state = DeliveryState(repo, True, "run-phase", "scope", None, None, None, (), (), scratch_ref="delivery/fixture")
    compiled = compiler.compile_delivery(repo, state, config, run_id=run_id)
elif kind == "maintenance":
    act, target, mode = sys.argv[5:8]
    compiled = compiler.compile_maintenance(repo, act, int(target) if target else None, MaintenanceMode(mode), config, run_id=run_id, source_revision="a" * 40)
else:
    target = PromotionTarget("production", TargetKind.ENVIRONMENT, "commit", "version", "probe", install="test", environment="production")
    compiled = compiler.compile_promotion(repo, target, "1.0.0", config, run_id=run_id, source_revision="a" * 40)
payload = json.loads(compiled.executor_payload)
payload["status"] = {"phase": phase}
json.dump(run_dto(parse_runs({"items": [payload]})[0]), sys.stdout)
