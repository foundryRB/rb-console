"""A gate's export, the worker's prompt and the cockpit's studio reads name the project the
studio holds, by that studio's own naming rule (INT-FC-R151)."""
from __future__ import annotations

import pytest
from pytest_intent import intent
from test_catalog_agents import _catalog, _env, _fresh_state, _workers

from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway
from orchestrator.domain.delivery import SEQUENCE, studio_project_key
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.delivery_launch import build_worker_launch


@intent("INT-FC-R151")
@pytest.mark.parametrize(("studio", "slug", "key"), [
    ("estimatekit", "SolveOS", "SolveOS"),
    ("protopane", "SolveOS", "solveos"),
    ("protopane", "Solve_OS.v2", "solve-os-v2"),
    ("protopane", "foundry-console", "foundry-console"),
    ("protopane", "---", "project"),
    ("platform-studio", "SolveOS", "SolveOS"),
])
def test_each_studio_keys_a_delivery_by_its_own_naming_rule(studio, slug, key):
    assert studio_project_key(studio, slug) == key


@intent("INT-FC-R151")
def test_a_new_lines_tooled_gates_name_the_key_each_studio_will_hold(tmp_path):
    """The keys are known before the phase creates the project: a new SolveOS line's design
    export names `solveos`, the key protopane gives a prototype named `SolveOS`."""
    urls = {"estimatekit": "http://ek:8001", "protopane": "http://pp:8801"}
    wf = compile_workflow("PSA/SolveOS", _fresh_state(tmp_path), RunConfig("tok", "PSA/SolveOS", True, RunMode.ONE_SHOT),
                          run_id="r1", catalog=_catalog(), tool_urls=urls)
    workers = _workers(wf)
    for phase in SEQUENCE:
        env = _env(workers[f"worker-{phase.name.replace('+', '-')}"])
        assert env["FC_SLUG"]["value"] == studio_project_key(phase.studio, "SolveOS")
    assert _env(workers["worker-scope"])["FC_SLUG"]["value"] == "SolveOS"
    assert _env(workers["worker-design"])["FC_SLUG"]["value"] == "solveos"


@intent("INT-FC-R151")
def test_the_design_worker_is_told_the_key_its_prototype_will_hold():
    prompt = build_worker_launch("PSA/SolveOS", "design", "design-session",
                                 RunConfig("tok", "PSA/SolveOS", True, RunMode.ONE_SHOT)).prompt
    assert "estimatekit as `SolveOS`" in prompt
    assert "protopane as `solveos`" in prompt and "named `SolveOS`" in prompt


@intent("INT-FC-R151")
def test_the_cockpit_reads_a_prototype_by_the_key_protopane_holds(monkeypatch):
    gateway = HttpStudioGateway(config=None, domain="test.example")
    monkeypatch.setattr(gateway, "_prototype_projects", lambda: [{"slug": "solveos", "screen_count": 50},
                                                                 {"slug": "solve-os", "screen_count": 3}])
    monkeypatch.setattr(gateway, "estimatekit_slugs", lambda: {"SolveOS"})
    monkeypatch.setattr(gateway, "platform_apps", list)
    artifacts = gateway.artifacts_for("SolveOS")
    assert artifacts["design"].exists is True and artifacts["design"].url.endswith("/p/solveos")
    assert artifacts["design"].detail == "50 screens"
    assert artifacts["proposal"].exists is True and artifacts["proposal"].url.endswith("/projects/SolveOS")
    asked = []
    monkeypatch.setattr(gateway, "_rest", lambda studio, path, **kwargs: asked.append(path) or {})
    gateway.design_substance("SolveOS", studio="protopane")
    assert asked == ["/api/projects/solveos/export"]
