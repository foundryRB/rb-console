from delivery_fixtures import record_inputs
"""Install facts belong to constructed compilers, independent of later environment."""
import json
from dataclasses import replace

import pytest

from orchestrator.adapters.outbound.argo.argo_workflow_compiler import ArgoWorkflowCompiler
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.services.delivery_resolution import derive_from_records


def compile_kind(compiler, kind):
    cfg=RunConfig("credential","org/app",True)
    common={"run_id":"run","worker_image":"registry/worker:1.0.0"}
    if kind=="delivery":
        state=replace(derive_from_records("org/app",True,record_inputs({})),scratch_ref="delivery/line")
        workflow=compiler.compile_delivery("org/app",state,cfg,**common)
    elif kind=="maintenance":
        workflow=compiler.compile_maintenance("org/app","resolve",1,MaintenanceMode.GATED,cfg,source_revision="a"*40,**common)
    else:
        target=PromotionTarget("prod",TargetKind.ENVIRONMENT,"","","",install="foundry",environment="prod")
        workflow=compiler.compile_promotion("org/app",target,"1.0.0",cfg,source_revision="a"*40,**common)
    data=json.loads(workflow.executor_payload)
    return {entry["value"] for template in data["spec"]["templates"] if "container" in template for entry in template["container"]["env"] if entry["name"]=="FC_DOMAIN"}


@pytest.mark.parametrize("kind",["delivery","maintenance","promotion"])
def test_compiler_instances_keep_independent_domains_despite_environment_changes(monkeypatch,kind):
    monkeypatch.setenv("FC_DOMAIN","ambient.example")
    first=ArgoWorkflowCompiler(public_domain="first.example")
    second=ArgoWorkflowCompiler(public_domain="second.example")
    monkeypatch.setenv("FC_DOMAIN","changed.example")
    assert compile_kind(first,kind)=={"first.example"}
    assert compile_kind(second,kind)=={"second.example"}
    assert compile_kind(ArgoWorkflowCompiler(),kind)=={""}


def test_factory_reads_domain_at_each_construction(monkeypatch):
    from orchestrator import container
    monkeypatch.setenv("FC_ORG","org")
    monkeypatch.setenv("FC_WORKER_IMAGE","registry/worker:1.0.0")
    monkeypatch.setattr(container,"build_capabilities",lambda *args,**kwargs:kwargs)
    monkeypatch.setattr(container,"FileRunLogStore",lambda:object())
    monkeypatch.setattr(container,"resolve_event_publisher",lambda:None)
    monkeypatch.setenv("FC_DOMAIN","first.example")
    first=container.build_service()
    monkeypatch.setenv("FC_DOMAIN","second.example")
    second=container.build_service()
    assert first["public_domain"]=="first.example"
    assert second["public_domain"]=="second.example"
