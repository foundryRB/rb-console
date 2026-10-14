from maintenance_fixtures import semantic_check, semantic_issue, semantic_pr, semantic_review
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from dataclasses import replace
from types import SimpleNamespace
import pytest
from orchestrator.application.use_cases.maintenance.maintenance_drive import MaintenanceDrive
from orchestrator.application.use_cases.promotion.promotion_drive import PromotionDrive
from orchestrator.application.services.operations.operation_admission import OperationAdmission
from orchestrator.domain.model.operation_receipt import OperationReceipt
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.repository_identity import RepositoryIdentity
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.permission_denied import PermissionDenied

class Receipts:
    def __init__(self): self.rows = {}
    def claim(self, key, fingerprint, *, authority, secret_write=False):
        if key in self.rows: return self.rows[key], False
        self.rows[key] = OperationReceipt(key, fingerprint, "claimed", secret_write, {})
        return self.rows[key], True
    def release_claim(self, key): self.rows.pop(key)
    def mark_dispatched(self, key, evidence): self.rows[key] = replace(self.rows[key], state="dispatched", evidence=evidence)
    def complete(self, key, result): self.rows[key] = replace(self.rows[key], state="completed", result=result)
    def unknown(self, key, reason): self.rows[key] = replace(self.rows[key], state="unknown", reason=reason)

class Credentials:
    def __init__(self, log): self.log = log
    def has_delivery(self, slug): self.log.append("credential-read"); return True
    def delivery_ref(self, slug): return "persisted"
    def run_ref(self, run_id): return "run-" + run_id
    def put(self, run_id, value): self.log.append("credential-write"); return self.run_ref(run_id)

class Source:
    def __init__(self, log): self.log = log
    def repository_revision(self, repo): self.log.append("head"); return "sha"
    def contract_text(self, repo, *, revision=""):
        assert revision == "sha"
        self.log.append("contract")
        return "targets:\n  - name: live\n    kind: environment\n    install: foundry\n    environment: prod\n"
    def deploy_installs(self, repo): return {"foundry": ["dev"]}
    def issue(self, repo, number): self.log.append("issue"); return semantic_issue({"state": "open"})
    def pr(self, repo, number): return semantic_pr({"state": "open", "head": {"sha": "sha"}})
    def pr_reviews(self, repo, number): return tuple(semantic_review(record) for record in ([]))
    def check_runs(self, repo, revision): return tuple(semantic_check(record) for record in ([]))
    def open_prs(self, repo): return tuple(semantic_pr(record) for record in ([]))
    def tags(self, repo): return ["v1.2.3"]

class Compiler:
    def __init__(self, log, fail=False): self.log = log; self.fail = fail
    def compile_maintenance(self, *args, **kwargs):
        self.log.append("compile")
        if self.fail: raise ValueError("invalid pinned compilation")
        assert kwargs["source_revision"] == "sha"
        return CompiledWorkflow(kwargs["run_id"], kwargs["run_id"], args[0], "{}")
    compile_promotion = compile_maintenance

class Runner:
    def __init__(self, log, receipts, fail=False): self.log = log; self.receipts = receipts; self.fail = fail
    def submit(self, workflow):
        assert next(iter(self.receipts.rows.values())).state == "dispatched"
        self.log.append("submit")
        if self.fail: raise RuntimeError("response lost")
        return "workflow/" + workflow.name

def setup(kind, *, compile_fail=False, submit_fail=False):
    log=[]; receipts=Receipts(); source=Source(log)
    agents=[CatalogAgent(name, name, "", (), (), "", True, False, "") for name in ["programmer", "reviewer", "release-manager"]]
    config=SimpleNamespace(get_setting=lambda key: {"configured": True, "name": "actor"} if key.startswith("gitid-") else {})
    common=dict(config=config, credentials=Credentials(log), msource=source, psource=source,
        studios=SimpleNamespace(agent_catalog=lambda: agents), worker_image="worker:1", workflows=Runner(log,receipts,submit_fail),
        cap_git_roles=SimpleNamespace(execute=lambda: {name: "actor" for name in ["programmer", "reviewer", "release-manager"]}),
        cap_pair_credential_held=SimpleNamespace(execute=lambda name: True),
        cap_run_retention=SimpleNamespace(execute=lambda: {}),
        admission=OperationAdmission(receipts), compiler=Compiler(log,compile_fail),
        incarnations=SimpleNamespace(verify_current=lambda repo: RepositoryIdentity("org/app", "123")))
    if kind=="maintenance":
        common.update(observations=None,door=None,events=None,cap_instantiation=None,cap_list_git_identities=None)
        service=MaintenanceDrive(**common)
        call=lambda context, **kw: service.execute("org/app", "resolve", 7, "gated", RunConfig("secret", "org/app", True), context=context, operation_id="op", **kw)
    else:
        service=PromotionDrive(**common)
        call=lambda context, **kw: service.execute("org/app", "live", "1.2.3", context=context, operation_id="op", **kw)
    context=CommandContext("human","operator","grant",frozenset({kind+".drive"}),frozenset({"org/app"}),"1","org")
    return call,context,log,receipts

@pytest.mark.parametrize("kind", ["maintenance", "promotion"])
def test_authority_precedes_reads(kind):
    call,context,log,receipts=setup(kind)
    with pytest.raises(PermissionDenied): call(replace(context, allowed_actions=frozenset()))
    assert log == [] and receipts.rows == {}

@pytest.mark.parametrize("kind", ["maintenance", "promotion"])
def test_source_revision_conflict_has_no_effect(kind):
    call,context,log,receipts=setup(kind)
    with pytest.raises(Conflict): call(context,expected_revision="old")
    assert "credential-write" not in log and "submit" not in log and receipts.rows == {}

@pytest.mark.parametrize("kind", ["maintenance", "promotion"])
def test_compile_refusal_before_credential_write(kind):
    call,context,log,receipts=setup(kind,compile_fail=True)
    with pytest.raises(ValueError): call(context)
    assert "credential-write" not in log and "submit" not in log and receipts.rows == {}

@pytest.mark.parametrize("kind", ["maintenance", "promotion"])
def test_completed_replay_submits_once(kind):
    call,context,log,receipts=setup(kind)
    result=call(context)
    assert call(context)==result
    assert log.count("head")==1 and log.count("compile")==1 and log.count("submit")==1
    if kind=="maintenance": assert log.index("compile") < log.index("credential-write") < log.index("submit")

@pytest.mark.parametrize("kind", ["maintenance", "promotion"])
def test_unknown_retry_never_submits_second_workflow(kind):
    call,context,log,receipts=setup(kind,submit_fail=True)
    with pytest.raises(OperationUnknown): call(context)
    with pytest.raises(OperationUnknown): call(context)
    assert log.count("compile")==1 and log.count("submit")==1
