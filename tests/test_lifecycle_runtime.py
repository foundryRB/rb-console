"""A pinned phase addition and removal changes resolution and execution together."""
from __future__ import annotations
from delivery_fixtures import record_inputs

from dataclasses import replace
from types import SimpleNamespace
import json

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.records.lifecycle_codec import (
    decode_lifecycle,
    decode_pin,
    encode_lifecycle,
    encode_pin,
    lifecycle_digest,
)
from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.domain.current_lifecycle import (
    CURRENT_LIFECYCLE,
    CURRENT_PLAYBOOK_REF,
)
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.services.delivery_resolution import derive_from_records
from orchestrator.application.use_cases.content.phase_substance import PhaseSubstance
from orchestrator.application.use_cases.studios.tool_urls import ToolUrls
from orchestrator.adapters.inbound.http.mappers.delivery import overview_dto
from orchestrator.domain.model.delivery_overview import DeliveryOverview
from orchestrator.domain.model.studio_artifact import StudioArtifact


@intent("INT-FC-R167")
def test_record_phase_addition_and_removal_changes_resolver_and_compiler() -> None:
    initial = CURRENT_LIFECYCLE
    extra = replace(initial.phases[1], name="inspect", label="Inspect", record="inspection.md", gate="inspection", inputs=("design",), artifact="record")
    phases = list(initial.phases)
    phases.insert(2, extra)
    phases[3] = replace(phases[3], inputs=("inspect",))
    changed = replace(initial, version="1.1.0", phases=tuple(phases))
    records = {p.record: f"---\nstatus: complete\ngate: {p.gate}\nsigned: 2026-10-05\n---\n" for p in initial.phases[:2]}
    state = replace(derive_from_records("o/app", True, record_inputs(records), changed), scratch_ref="delivery/line")
    assert state.phase == "inspect"
    workflow = compile_workflow("o/app", state, RunConfig("secret", "o/app", True), run_id="test", worker_image="registry/worker:1.0.0", definition=changed)
    worker = next(t for t in workflow["spec"]["templates"] if t["name"] == "worker-inspect")
    env = {row["name"]: row.get("value") for row in worker["container"]["env"]}
    assert env["FC_RECORD"] == "inspection.md"
    assert env["FC_LIFECYCLE_DIGEST"] == lifecycle_digest(changed)
    assert env["FC_PLAYBOOK_REF"] == CURRENT_PLAYBOOK_REF
    assert "/opt/foundry/playbook/" in worker["container"]["args"][0]
    assert "Pull the skill" not in worker["container"]["args"][0]
    removed = replace(initial, version="1.2.0", phases=(initial.phases[0], replace(initial.phases[2], inputs=("scope",)), *initial.phases[3:]))
    state = replace(derive_from_records("o/app", True, record_inputs(records), removed), scratch_ref="delivery/line")
    assert state.phase == "intent+plan"
    workflow = compile_workflow("o/app", state, RunConfig("secret", "o/app", True), run_id="removed", definition=removed)
    assert all(t["name"] != "worker-design" for t in workflow["spec"]["templates"])
    # The original pinned definition continues to govern its line.
    assert derive_from_records("o/app", True, record_inputs(records), initial).phase == "intent+plan"


@intent("INT-FC-R167")
def test_unsupported_handlers_and_unresolved_dependencies_are_refused() -> None:
    payload = encode_lifecycle(CURRENT_LIFECYCLE)
    payload["phases"][0]["completion"] = "loop"
    with pytest.raises(ValueError):
        decode_lifecycle(payload)
    payload = encode_lifecycle(CURRENT_LIFECYCLE)
    payload["phases"][0]["inputs"] = ["learn"]
    with pytest.raises(ValueError):
        decode_lifecycle(payload)


@intent("INT-FC-R167")
@pytest.mark.parametrize("artifact", ["absent", "unsupported"])
def test_artifact_contract_refuses_missing_and_unknown_handlers(artifact: str) -> None:
    payload = encode_lifecycle(CURRENT_LIFECYCLE)
    if artifact == "absent":
        del payload["phases"][1]["artifact"]
    else:
        payload["phases"][1]["artifact"] = "loop"
    with pytest.raises(ValueError, match="artifact"):
        decode_lifecycle(payload)


@intent("INT-FC-R167", "INT-FC-R53", "INT-FC-R120")
def test_added_design_artifact_drives_content_export_url_and_cockpit() -> None:
    initial = CURRENT_LIFECYCLE
    extra = replace(initial.phases[1], name="inspect", label="Inspect", record="inspection.md", gate="inspection", inputs=("design",))
    phases = list(initial.phases)
    phases.insert(2, extra)
    phases[3] = replace(phases[3], inputs=("inspect",))
    changed = replace(initial, version="1.1.0", phases=tuple(phases))
    records = {p.record: f"---\nstatus: complete\ngate: {p.gate}\nsigned: 2026-10-05\n---\n" for p in initial.phases[:2]}
    state = replace(derive_from_records("o/app", True, record_inputs(records), changed), scratch_ref="delivery/line")
    calls = []

    class Studios:
        def tool_url(self, studio):
            return f"http://{studio}.internal"

        def design_substance(self, slug, *, studio):
            calls.append((slug, studio))
            return {"theme_css": "configured-theme"}

    studios = Studios()
    content = PhaseSubstance(studios=studios, cap_repo_file=None, cap_status=SimpleNamespace(execute=lambda repo: state))
    assert content.execute("o/app", "inspect") == {"theme_css": "configured-theme"}
    assert calls == [("app", "protopane")]
    urls = ToolUrls(studios=studios).execute(changed)
    workflow = compile_workflow("o/app", state, RunConfig("secret", "o/app", True), run_id="inspection", tool_urls=urls, definition=changed)
    worker = next(t for t in workflow["spec"]["templates"] if t["name"] == "worker-inspect")
    env = {row["name"]: row.get("value") for row in worker["container"]["env"]}
    assert env["FC_TOOL_URL"] == "http://protopane.internal"
    assert env["FC_ARTIFACT"] == "design"
    assert json.loads(env["FC_LIFECYCLE_DEFINITION"]) == encode_lifecycle(changed)
    assert env["FC_LIFECYCLE_DIGEST"] == lifecycle_digest(changed)
    artifact = StudioArtifact("protopane", True, True, "https://prototype/inspection")
    overview = overview_dto(DeliveryOverview(state, {"design": artifact}))
    inspection = next(phase for phase in overview["phases"] if phase["name"] == "inspect")
    assert inspection["renderer"] == "design"
    assert inspection["artifact"]["url"] == artifact.url


def test_journal_handler_finishes_from_committed_learned_stamp() -> None:
    records = {p.record: f"---\nstatus: complete\ngate: {p.gate}\nsigned: 2026-10-05\n---\n" for p in CURRENT_LIFECYCLE.phases if p.completion == "record"}
    assert derive_from_records("o/app", True, record_inputs(records)).status == "delivered"
    records["journal.md"] = "---\nlearned: 2026-10-05\n---\n"
    state = derive_from_records("o/app", True, record_inputs(records))
    assert state.status == "learned"
    assert state.learned_on == "2026-10-05"


@intent("INT-FC-R167")
def test_compiler_uses_line_definition_and_its_pinned_content_revision() -> None:
    pinned = replace(CURRENT_LIFECYCLE, source_ref="a" * 40)
    state = replace(derive_from_records("o/app", True, record_inputs({}), pinned), scratch_ref="delivery/line")
    workflow = compile_workflow("o/app", state, RunConfig("secret", "o/app", True), run_id="pinned")
    workers = [row for row in workflow["spec"]["templates"] if "container" in row]
    assert workers
    for worker in workers:
        env = {row["name"]: row.get("value") for row in worker["container"]["env"]}
        assert env["FC_PLAYBOOK_REF"] == "a" * 40


# A lifecycle pin as a line's config.json carries it. Its bytes and digest are a contract
# with every line already captured: the codec must keep reading it unchanged.
_CAPTURED_PIN = """{
  "schema_version": 1,
  "id": "foundry-delivery",
  "version": "1.0.0",
  "phases": [
    {
      "id": "scope",
      "label": "Scope",
      "skill": "deliver-engagement",
      "agent": "architect",
      "record": "proposal.md",
      "gate": "proposal",
      "question": "What is asked, and what would it cost?",
      "studio": "estimatekit",
      "completion": "record",
      "inputs": [],
      "artifact": "proposal",
      "tool": "the estimation engine (`REF-Estimation.md`)"
    },
    {
      "id": "design",
      "label": "Design",
      "skill": "design-session",
      "agent": "designer",
      "record": "design.md",
      "gate": "design",
      "question": "What should it look and feel like?",
      "studio": "protopane",
      "completion": "record",
      "inputs": [
        "scope"
      ],
      "artifact": "design",
      "tool": "the prototyping hub (`REF-Design.md`)"
    },
    {
      "id": "intent+plan",
      "label": "Intent + plan",
      "skill": "intent-session",
      "agent": "planner",
      "record": "handoff.md",
      "gate": "plan",
      "question": "What must be true, and how do we build it?",
      "studio": "",
      "completion": "record",
      "inputs": [
        "design"
      ],
      "artifact": "handoff",
      "tool": "CSD intent authoring (`REF-CSD.md`)"
    },
    {
      "id": "build+ship",
      "label": "Build + ship",
      "skill": "run-delivery-plan",
      "agent": "builder",
      "record": "build.md",
      "gate": "delivery",
      "question": "Is it working software, and is it live?",
      "studio": "platform-studio",
      "completion": "record",
      "inputs": [
        "intent+plan"
      ],
      "artifact": "build",
      "tool": "the platform (`REF-AppContract.md`)"
    },
    {
      "id": "learn",
      "label": "Learn",
      "skill": "reconcile-delivery",
      "agent": "librarian",
      "record": "journal.md",
      "gate": null,
      "question": "What did it teach, and what comes next?",
      "studio": "playbook-studio",
      "completion": "journal",
      "inputs": [
        "build+ship"
      ],
      "artifact": null,
      "tool": "the playbook (`REF-Authoring.md`)"
    }
  ],
  "source_ref": "596f312afd507e14facd07196dede34503fd6d3c",
  "digest": "cd870be39d3837cb0f50a6f979e44d6b1a279f6e776278ab60eb1d44b6e49390",
  "worker_image": "registry.example/worker:1.0.0"
}"""


@intent("INT-FC-R167")
def test_a_captured_pin_keeps_its_digest_meaning_and_bytes() -> None:
    pin = json.loads(_CAPTURED_PIN)
    definition = decode_pin(pin)
    assert lifecycle_digest(definition) == pin["digest"] == "cd870be39d3837cb0f50a6f979e44d6b1a279f6e776278ab60eb1d44b6e49390"
    assert [(p.name, p.record, p.gate, p.inputs) for p in definition.phases] == [
        ("scope", "proposal.md", "proposal", ()),
        ("design", "design.md", "design", ("scope",)),
        ("intent+plan", "handoff.md", "plan", ("design",)),
        ("build+ship", "build.md", "delivery", ("intent+plan",)),
        ("learn", "journal.md", "", ("build+ship",)),
    ]
    assert (definition.source_ref, definition.worker_image) == (pin["source_ref"], pin["worker_image"])
    assert json.dumps(encode_pin(definition), indent=2) == _CAPTURED_PIN


@intent("INT-FC-R167")
def test_the_repository_store_commits_the_captured_pin_beside_the_line_configuration(monkeypatch) -> None:
    import base64
    from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
    store = GitHubRepoStore("org", lambda: "token")
    puts = []
    def request(method, path, token, body=None):
        if method == "PUT":
            puts.append(json.loads(base64.b64decode(body["content"])))
        return {"sha": "c" * 40}
    monkeypatch.setattr(store, "_req", request)
    monkeypatch.setattr(store, "_require_line_ref", lambda *args: "delivery/line")
    captured = replace(CURRENT_LIFECYCLE, source_ref=CURRENT_PLAYBOOK_REF, worker_image="registry.example/worker:1.0.0")
    store.write_config("org/app", {"mode": "one-shot"}, lifecycle=captured)
    assert puts == [{"mode": "one-shot", "lifecycle": encode_pin(captured)}]
    assert decode_pin(puts[0]["lifecycle"]) == captured
