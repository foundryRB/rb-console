from maintenance_fixtures import semantic_pr
from types import SimpleNamespace
import pytest
from pytest_intent import intent
from orchestrator.application.services.maintenance.redrive_oneshot import helper_redrive_oneshot
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext

class Source:
    def __init__(self, log, pr): self.log=log; self.response=pr
    def pr(self, repo, number):
        self.log.append(("source",repo,number))
        if isinstance(self.response, Exception): raise self.response
        return semantic_pr(self.response)

class Door:
    def __init__(self, log, pr): self.log=log; self.response=pr
    def pull_request(self, repo, number, credential):
        self.log.append(("door",repo,number,credential))
        return semantic_pr(self.response)

class Credentials:
    def __init__(self, log): self.log=log
    def has_delivery(self, slug): self.log.append(("credential-read",slug)); return True
    def delivery_ref(self, slug): return "credential-ref"

class Compiler:
    def __init__(self, log): self.log=log
    def compile_maintenance(self, repo, *args, **kwargs):
        self.log.append(("compile",kwargs["source_revision"]))
        assert len(kwargs["source_revision"]) == 40
        return CompiledWorkflow(kwargs["run_id"],kwargs["run_id"],repo,"{}")

class Runner:
    def __init__(self, log): self.log=log
    def submit(self, workflow):
        assert isinstance(workflow, CompiledWorkflow)
        self.log.append(("submit",workflow.repository))
        return "workflow/"+workflow.name


def invoke(pr, home=None, *, context=None, log=None):
    log=[] if log is None else log
    entry={}; observations=SimpleNamespace(oneshot={})
    context=context or CommandContext("scheduler","local","original-grant",frozenset({"maintenance.drive"}),frozenset({"org/app"}),"rev","org")
    helper_redrive_oneshot("old-handle",entry,"org/app",7,8,1,findings="recorded failed review",home=home,
        observations=observations,config=None,credentials=Credentials(log),studios=None,worker_image="worker:1",workflows=Runner(log),
        cap_delivery_config=SimpleNamespace(execute=lambda repo: {"mode":"interactive","provider":"claude","base_url":"","model":""}),
        cap_git_roles=SimpleNamespace(execute=lambda:{}),cap_pair_credential_held=SimpleNamespace(execute=lambda key: True),
        cap_run_retention=SimpleNamespace(execute=lambda:{}),compiler=Compiler(log),msource=Source(log,pr),door=Door(log,pr),context=context)
    return log,entry,observations

@intent("INT-FC-R75")
def test_redrive_pins_fresh_open_failed_pr_head_before_credential_read():
    log,entry,observations=invoke({"state":"open","head":{"sha":"a"*40}})
    assert log[0] == ("source","org/app",8)
    assert [row[0] for row in log] == ["source","credential-read","compile","submit"]
    assert log[2] == ("compile","a"*40)
    assert len(observations.oneshot)==1

@intent("INT-FC-R131")
def test_managed_redrive_reads_and_pins_pair_pr_only():
    home=PromotionTarget("home",TargetKind.REPOSITORY,"","","",repo="foreign/app",branch="main",credential="pair-key")
    log,entry,observations=invoke({"state":"open","head":{"sha":"b"*40}},home)
    assert log[0] == ("door","foreign/app",8,"pair-key")
    assert not any(row[0]=="source" for row in log)
    assert ("compile","b"*40) in log
    assert len(observations.oneshot)==1

@intent("INT-FC-R75")
@pytest.mark.parametrize("pr", [{}, {"state":"closed","head":{"sha":"a"*40}}, {"state":"open","head":{}}, {"state":"open","head":{"sha":"branch-name"}}, SourceUnavailable("offline")])
def test_unavailable_head_parks_before_credentials_compile_or_effect(pr):
    log,entry,observations=invoke(pr)
    assert [row[0] for row in log] == ["source"]
    assert entry["acted"] and "source revision unavailable" in entry["result"]
    assert observations.oneshot == {}

@intent("INT-FC-R75")
def test_wrong_repository_grant_refuses_before_any_source_or_credential_read():
    log=[]
    context=CommandContext("scheduler","local","original-grant",frozenset({"maintenance.drive"}),frozenset({"org/other"}),"rev","org")
    with pytest.raises(PermissionDenied):
        invoke({"state":"open","head":{"sha":"a"*40}},context=context,log=log)
    assert log==[]
