"""The Argo compiler: one worker step per remaining phase, mode-aware gate suspends,
bounded retries, and a credential referenced by Secret, never inlined."""
from dataclasses import replace

import pytest
from pytest_intent import intent

from orchestrator.domain.services.delivery_launch import HEADLESS_TURN
from orchestrator.adapters.outbound.argo.maintenance_launch import compile_maintenance_workflow
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from orchestrator.domain.services.run_policy import _DEGRADED_EXIT, _DELIVERY_SCALE_EXIT, _STAMP_REFUSED_EXIT, _TERMINAL_EXITS
from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode


def _fresh_state(tmp_path):
    scratch = tmp_path / "acme" / ".delivery"
    scratch.mkdir(parents=True)
    (scratch / "README.md").write_text("scratch", encoding="utf-8")
    # The line's resolved scratch ref rides the state the way the remote source attaches
    # it; the compiler refuses a delivery run without one.
    return replace(derive_state(str(tmp_path / "acme")), scratch_ref="delivery/2026-08-18")


INTER = RunConfig("tok", "acme", True, RunMode.INTERACTIVE)
ONE = RunConfig("tok", "acme", True, RunMode.ONE_SHOT)


@intent("INT-FC-R23")
def test_a_worker_step_per_remaining_phase(tmp_path):
    wf = compile_workflow("acme", _fresh_state(tmp_path), INTER, run_id="r1")
    names = {t["name"] for t in wf["spec"]["templates"]}
    for expected in ("worker-scope", "worker-design", "worker-intent-plan", "worker-build-ship"):
        assert expected in names
    # Every pod label value must be k8s-legal: 'intent+plan' carries its slug, not its
    # display name (a live run died on pod validation the first time a line reached it).
    for t in wf["spec"]["templates"]:
        if t["name"].startswith("worker-"):
            assert "+" not in t["metadata"]["labels"]["foundry-console/phase"]


@intent("INT-FC-R24")
def test_interactive_suspends_at_gates_one_shot_does_not(tmp_path):
    state = _fresh_state(tmp_path)
    inter = compile_workflow("acme", state, INTER, run_id="r1")
    one = compile_workflow("acme", state, ONE, run_id="r1")

    def suspends(wf):
        return [t for t in wf["spec"]["templates"] if "suspend" in t]

    def gate_steps(wf):
        line = next(t for t in wf["spec"]["templates"] if t["name"] == "line")
        return [step for group in line["steps"] for step in group if step["name"].startswith("gate-")]

    # One per gate: proposal, design, plan, delivery, each waiting unconditionally.
    assert len(suspends(inter)) == 4
    assert len(gate_steps(inter)) == 4
    assert all("when" not in step for step in gate_steps(inter))
    # One-shot closes its own gates: no suspend template and no gate step.
    assert suspends(one) == []
    assert gate_steps(one) == []


@intent("INT-FC-R181")
def test_a_refused_one_shot_stamp_is_a_terminal_exit_no_worker_retries(tmp_path):
    # The worker ends a step whose stamp refused over a passing review on this code; a retry
    # would re-run the whole phase into the same closure, so every compiled worker refuses it.
    assert _STAMP_REFUSED_EXIT in _TERMINAL_EXITS
    wf = compile_workflow("acme", _fresh_state(tmp_path), ONE, run_id="r1")
    workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
    assert workers
    for t in workers:
        assert f"lastRetry.exitCode != '{_STAMP_REFUSED_EXIT}'" in t["retryStrategy"]["expression"]


@intent("INT-FC-R182")
def test_every_worker_step_reports_its_refusal_output(tmp_path):
    wf = compile_workflow("acme", _fresh_state(tmp_path), ONE, run_id="r1")
    workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
    assert workers
    for t in workers:
        params = {p["name"]: p["valueFrom"] for p in t["outputs"]["parameters"]}
        # The path is the entrypoint's FC_REFUSAL_FILE default.
        assert params == {"refusal": {"path": "/tmp/fc-refusal", "default": ""}}


@intent("INT-FC-R25")
def test_worker_templates_are_bounded_and_reference_credentials_by_ref(tmp_path):
    state = _fresh_state(tmp_path)
    wf = compile_workflow("acme", state, INTER, run_id="r1", max_attempts=3)
    workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
    assert workers
    for t in workers:
        assert t["retryStrategy"]["limit"] == 3
        # No terminal stop (64 degraded, 65 delivery-scale, 66 wrong-repo) is retried; every
        # other failure is. The expression is what keeps the executor from blind-retrying a
        # blocker it cannot clear (and redoing the whole phase). Built from _TERMINAL_EXITS
        # rather than frozen as a literal: a frozen expected string makes every new terminal
        # stop look like a regression here, and the fix - editing the literal - is the same
        # hand-sync this file exists to check.
        assert t["retryStrategy"]["expression"] == " && ".join(
            f"lastRetry.exitCode != '{code}'" for code in _TERMINAL_EXITS
        )
        assert t["activeDeadlineSeconds"] > 0
        env = {e["name"]: e for e in t["container"]["env"]}
        # the per-run model credential is by-ref, never inline
        assert "valueFrom" in env["FC_MODEL_CREDENTIAL"] and "value" not in env["FC_MODEL_CREDENTIAL"]
        # no git identity is assigned to these phases, so no FC_GIT_* env rides at all: the
        # worker has no git credentials until an identity is configured and assigned (no default)
        assert "FC_GIT_TOKEN" not in env and "FC_GIT_USER" not in env
        assert env["FC_PROVIDER"]["value"] == "claude"  # the per-run provider
        assert "FC_MODEL" in env and "FC_BASE_URL" in env  # model + endpoint, distinct from the secret
        # MCP is per door and Basic auth: a scope worker reaches playbook-studio + estimatekit,
        # each with its own user + password ref, not a shared token
        assert "FC_MCP_SCHEME" not in env and "FC_MCP_TOKEN" not in env
        scope = next(t for t in workers if t["name"] == "worker-scope")
        senv = {e["name"] for e in scope["container"]["env"]}
        assert {"FC_MCP_PLAYBOOK_STUDIO_USER", "FC_MCP_PLAYBOOK_STUDIO_PASS"} <= senv
        assert {"FC_MCP_ESTIMATEKIT_USER", "FC_MCP_ESTIMATEKIT_PASS"} <= senv

    # The activeDeadlineSeconds is the delivery's configured worker budget (INT-FC-R76), not a
    # flat constant: a from-scratch build+ship needs hours, so a custom timeout flows through to
    # every worker's deadline. The RunConfig default is an hour (was a fatal flat 30 min).
    assert all(t["activeDeadlineSeconds"] == 3600 for t in workers)
    custom = compile_workflow("acme", state, replace(INTER, worker_timeout_seconds=7200), run_id="r2")
    assert all(
        t["activeDeadlineSeconds"] == 7200
        for t in custom["spec"]["templates"]
        if t["name"].startswith("worker-")
    )


@intent("INT-FC-R31")
def test_the_resolved_scratch_ref_rides_every_delivery_worker(tmp_path):
    # The scratch ref is resolved per-repo state (DeliveryState.scratch_ref), and a
    # compiled run threads it to the pod as FC_SCRATCH_REF so the entrypoint can mount
    # the line's worktree and push the ref by name. Every delivery worker in the line
    # carries it; a maintenance worker (no scratch) compiles with it empty.
    state = _fresh_state(tmp_path)
    wf = compile_workflow("acme", state, INTER, run_id="r1")
    workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
    assert workers
    for t in workers:
        env = {e["name"]: e.get("value") for e in t["container"]["env"]}
        assert env["FC_SCRATCH_REF"] == "delivery/2026-08-18"

    maint = compile_maintenance_workflow(
        "example-org/acme", "resolve", 7, MaintenanceMode.GATED, RunConfig("tok", "acme", True),
        run_id="m1",
    )
    for t in maint["spec"]["templates"]:
        if t["name"].startswith("worker-"):
            env = {e["name"]: e.get("value") for e in t["container"]["env"]}
            assert env["FC_SCRATCH_REF"] == ""


@intent("INT-FC-R31")
def test_compile_refuses_a_delivery_run_without_a_scratch_ref(tmp_path):
    # A delivery worker mounts the line's ref and pushes it by name, so a run compiled
    # without one would burn its whole turn and die late on a malformed refspec. The
    # refusal names the reason the resolution is empty; the maintenance compiler stays
    # untouched - its workers carry no scratch.
    from orchestrator.adapters.outbound.github.delivery_contract import _anomalous

    # Never established: nothing to mount, nothing to push to.
    bare = derive_state(str(tmp_path / "bare"))
    with pytest.raises(ValueError, match="establish the delivery first"):
        compile_workflow("bare", bare, INTER, run_id="r1")
    # The two-ref anomaly: the derived state carries the reason and the refusal
    # surfaces it verbatim, so the operator reads which refs collide.
    anomaly = _anomalous("acme", ["delivery/2026-08-01", "delivery/2026-08-18"])
    with pytest.raises(ValueError, match="delivery/2026-08-01"):
        compile_workflow("acme", anomaly, INTER, run_id="r1")
    # A maintenance workflow legitimately compiles with no scratch ref.
    maint = compile_maintenance_workflow(
        "example-org/acme", "resolve", 7, MaintenanceMode.GATED, RunConfig("tok", "acme", True),
        run_id="m1",
    )
    assert maint["spec"]["templates"]


@intent("INT-FC-R99")
def test_delivery_scale_exit_is_terminal_and_distinct_from_degraded(tmp_path):
    # The resolve worker emits exit 65 when it judges a ticket delivery-scale (too big for a
    # maintenance scope). Argo must NOT retry it - a blind retry cannot shrink the ticket - just
    # as it does not retry the degraded stop (64); and the two codes stay DISTINCT so the console
    # can tell a delivery-scale stop apart from a plain degraded blocker (issue #13). The rule
    # rides the one shared _worker_template, so BOTH compilers (delivery and maintenance) inherit it.
    assert _DEGRADED_EXIT != _DELIVERY_SCALE_EXIT
    # Membership, not the exact tuple: a new terminal stop (66, the wrong-repo park of
    # INT-FC-R113) must not break this claim's test, which is about 65 being terminal and
    # distinct. The tuple's own completeness is INT-FC-R113's gate (test_exit_contract.py).
    assert _DEGRADED_EXIT in _TERMINAL_EXITS
    assert _DELIVERY_SCALE_EXIT in _TERMINAL_EXITS
    state = _fresh_state(tmp_path)
    delivery = compile_workflow("acme", state, INTER, run_id="r1")
    maintenance = compile_maintenance_workflow(
        "org/app", "resolve", 13, MaintenanceMode.GATED,
        RunConfig("tok", "org/app", True), run_id="m1",
    )
    for wf in (delivery, maintenance):
        workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
        assert workers
        for t in workers:
            expr = t["retryStrategy"]["expression"]
            # both terminal codes fail fast; ' && ' means BOTH are required for a retry to fire
            assert f"lastRetry.exitCode != '{_DEGRADED_EXIT}'" in expr
            assert f"lastRetry.exitCode != '{_DELIVERY_SCALE_EXIT}'" in expr
            assert " && " in expr


@intent("INT-FC-R95")
def test_every_workflow_carries_a_pod_and_workflow_gc_policy(tmp_path):
    # Both compilers - delivery and maintenance - must splice the same GC policy into the
    # spec, or a finished run strands its worker pods (found live: a failed e2e drive left 75
    # Error-state pods stranded for days, because nothing GC'd a completed Workflow's pods).
    state = _fresh_state(tmp_path)
    delivery = compile_workflow("acme", state, ONE, run_id="r1")
    maintenance = compile_maintenance_workflow(
        "org/app", "resolve", 7, MaintenanceMode.ONE_SHOT,
        RunConfig("tok", "org/app", True), run_id="m1",
    )
    for wf in (delivery, maintenance):
        spec = wf["spec"]
        # podGC reclaims the worker pods on ANY terminal phase (success OR failure), so a
        # FAILED run cannot strand pods - OnWorkflowSuccess would leave exactly those behind.
        assert spec["podGC"]["strategy"] == "OnWorkflowCompletion"
        # A delay keeps the pod logs briefly readable while the operator inspects the run.
        assert spec["podGC"]["deleteDelayDuration"]
        # ttlStrategy reclaims the Workflow object too, a failed run's record kept longer than
        # a succeeded one's (the operator investigates failures, not greens).
        ttl = spec["ttlStrategy"]
        assert ttl["secondsAfterFailure"] > ttl["secondsAfterSuccess"] > 0

    # Fresh dicts per compile: mutating one workflow's policy never bleeds into another's.
    delivery["spec"]["podGC"]["strategy"] = "OnPodCompletion"
    other = compile_workflow("acme", state, ONE, run_id="r2")
    assert other["spec"]["podGC"]["strategy"] == "OnWorkflowCompletion"


@intent("INT-FC-R48")
def test_worker_specifies_an_explicit_command(tmp_path):
    wf = compile_workflow("acme", _fresh_state(tmp_path), ONE, run_id="r1")
    workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
    assert workers
    for t in workers:
        # An explicit command so Argo's emissary runs the worker directly instead of resolving
        # the image ENTRYPOINT - that resolution reads the pull secret, which the workflow
        # controller cannot, so the pod would fail to start (found via a live drive).
        assert t["container"]["command"] == ["/usr/local/bin/worker-entrypoint.sh"]
        assert t["container"]["args"]  # the phase prompt is still passed as the arg


@intent("INT-FC-R49")
def test_from_phase_starts_mid_line_and_adopts_upstream_studios(tmp_path):
    state = _fresh_state(tmp_path)
    # Jump straight to build+ship: only that worker compiles (nothing upstream is re-run)...
    wf = compile_workflow("acme", state, ONE, run_id="r1", from_phase="build+ship")
    workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
    assert {t["name"] for t in workers} == {"worker-build-ship"}
    env = {e["name"] for e in workers[0]["container"]["env"]}
    # ...and it carries the adopted upstream doors (estimatekit for scope, protopane for design)
    # so it can read what it adopted, plus its own studio (platform-studio) and the playbook.
    assert {"FC_MCP_ESTIMATEKIT_USER", "FC_MCP_ESTIMATEKIT_PASS"} <= env
    assert {"FC_MCP_PROTOPANE_USER", "FC_MCP_PROTOPANE_PASS"} <= env
    prompt = workers[0]["container"]["args"][0]
    assert "adopted" in prompt.lower()  # the worker is told the upstream is adopted, not local

    # A normal full-line drive re-runs from scope and adopts nothing (the upstream doors are
    # only the scope worker's own studio, not bolted onto every worker).
    full = compile_workflow("acme", state, ONE, run_id="r2")
    design = next(t for t in full["spec"]["templates"] if t["name"] == "worker-design")
    denv = {e["name"] for e in design["container"]["env"]}
    assert not {"FC_MCP_ESTIMATEKIT_USER"} <= denv  # design didn't adopt scope's door


@intent("INT-FC-R158")
def test_every_compiled_delivery_worker_carries_the_landing_rule(tmp_path):
    # The rule is composed by build_worker_launch and the compiler appends its own directives
    # after it; what the pod runs is the container's argument, so the rule is asserted there, on
    # every phase of the line in both modes - build+ship, the phase that watches CI, above all.
    state = _fresh_state(tmp_path)
    for cfg in (INTER, ONE):
        wf = compile_workflow("acme", state, cfg, run_id="r1")
        workers = [t for t in wf["spec"]["templates"] if t["name"].startswith("worker-")]
        assert "worker-build-ship" in {t["name"] for t in workers}
        for t in workers:
            low = t["container"]["args"][0].lower()
            assert HEADLESS_TURN.lower() in low
            assert "foreground with a bounded polling loop" in low
            assert "never `in-progress`" in low
