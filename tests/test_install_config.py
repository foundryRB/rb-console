"""The GitHub owner and the worker image are install facts, read once at the composition
root with no default, and threaded into both launch compilers (ticket #54). A console
misconfigured for another organization must fail loud at start, never run wrongly against
the wrong org's issues, PRs, and registry (REF-AppContract section 1)."""
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.container import _require_install_value
from orchestrator.adapters.outbound.argo.maintenance_launch import compile_maintenance_workflow
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode

_ORG_LITERAL = "vfpt-vodafone-foundry"  # the reference install's owner, lower-cased


def _fresh_state(tmp_path):
    scratch = tmp_path / "acme" / ".delivery"
    scratch.mkdir(parents=True)
    (scratch / "README.md").write_text("scratch", encoding="utf-8")
    # The line's resolved scratch ref rides the state the way the remote source attaches
    # it; the compiler refuses a delivery run without one.
    return replace(derive_state(str(tmp_path / "acme")), scratch_ref="delivery/2026-08-18")


def test_missing_install_value_fails_loud_naming_the_key(monkeypatch):
    monkeypatch.delenv("FC_ORG", raising=False)
    with pytest.raises(RuntimeError) as exc:
        _require_install_value("FC_ORG")
    assert "FC_ORG" in str(exc.value)  # the message names the missing key, never a fallback


def test_blank_install_value_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("FC_WORKER_IMAGE", "   ")
    with pytest.raises(RuntimeError) as exc:
        _require_install_value("FC_WORKER_IMAGE")
    assert "FC_WORKER_IMAGE" in str(exc.value)


def test_set_install_value_is_returned_stripped(monkeypatch):
    monkeypatch.setenv("FC_ORG", "  Some-Org  ")
    assert _require_install_value("FC_ORG") == "Some-Org"


def test_both_compilers_stamp_the_injected_worker_image(tmp_path):
    image = "ghcr.io/some-install/foundry-console-worker:1.2.3"
    delivery = compile_workflow(
        "acme", _fresh_state(tmp_path), RunConfig("tok", "acme", True, RunMode.INTERACTIVE),
        run_id="r1", worker_image=image,
    )
    cfg = RunConfig(worker_credential="tok", repo_target="org/app", repo_rights=True)
    maintenance = compile_maintenance_workflow(
        "org/app", "resolve", 7, MaintenanceMode.GATED, cfg, run_id="m-1", worker_image=image,
    )
    for wf in (delivery, maintenance):
        workers = [t for t in wf["spec"]["templates"] if "container" in t]
        assert workers, "expected at least one worker template"
        for w in workers:
            assert w["container"]["image"] == image  # one definition feeds both launches


def test_no_worker_image_default_carries_an_owner(tmp_path):
    # The compilers carry NO owner-bearing default: absent an injected image the worker image
    # is empty, not one install's ghcr path, so a missing value can never silently ship wrong.
    wf = compile_workflow(
        "acme", _fresh_state(tmp_path), RunConfig("tok", "acme", True, RunMode.INTERACTIVE),
        run_id="r1",
    )
    worker = next(t for t in wf["spec"]["templates"] if "container" in t)
    assert _ORG_LITERAL not in worker["container"]["image"].lower()


def test_no_org_or_registry_owner_literal_in_orchestrator_runtime_source():
    # Acceptance: no GitHub org or registry-owner literal remains in orchestrator runtime
    # source (tests and fixtures may keep org names as fixture data, so tests/ is excluded).
    root = Path(__file__).resolve().parent.parent / "orchestrator"
    offenders = [
        str(p) for p in root.rglob("*.py")
        if _ORG_LITERAL in p.read_text(encoding="utf-8").lower()
    ]
    assert offenders == [], f"owner literal baked into runtime source: {offenders}"
