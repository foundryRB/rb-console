"""Stateful compare/delete tests exercise the shared transport's write-once path."""
import json
from urllib.error import HTTPError

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.github.buffered_response import BufferedResponse
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

A = "a" * 40
B = "b" * 40
T = "c" * 40
OTHER = "d" * 40
BRANCH = "refs/heads/delivery/line"
TAG = "refs/tags/delivered/app/P1"
ZERO = "0" * 40

class Host:
    """GitHub's refs as the close sees them. Like GitHub, updateRefs takes commit ids only
    and refuses a tag object; the REST refs API takes a tag object and refuses a ref that
    already exists."""
    def __init__(self, *, existing=None, race=None, lost=False, result=None):
        self.refs = {BRANCH: A}
        if existing: self.refs[TAG] = existing
        self.targets = {T: A, OTHER: B}
        self.race, self.lost, self.result = race, lost, result
        self.calls = []
    def open(self, request, timeout):
        method = request.get_method()
        path = request.full_url.removeprefix("https://api.github.com")
        body = json.loads(request.data) if request.data else None
        self.calls.append((method,path,body))
        if method == "GET":
            if path.endswith("/matching-refs/heads/delivery/"):
                return self.response([{"ref": BRANCH, "object": {"sha": self.refs[BRANCH]}}] if BRANCH in self.refs else [])
            if path == "/repos/org/app": return self.response({"node_id": "repository-node", "full_name": "org/app"})
            if "/git/ref/tags/" in path and TAG in self.refs:
                return self.response({"object": {"type": "tag", "sha": self.refs[TAG]}})
            if "/git/tags/" in path:
                oid = path.rsplit("/",1)[-1]
                return self.response({"object": {"type": "commit", "sha": self.targets[oid]}})
            raise HTTPError(request.full_url,404,"absent",{},None)
        if path.endswith("/git/tags"):
            assert body["object"] == A
            return self.response({"sha": T})
        if path.endswith("/git/refs"):
            if self.race == "ruleset":
                raise HTTPError(request.full_url,422,"Repository rule violations found",{},None)
            if self.race == "tag": self.refs[TAG] = OTHER
            if self.race == "same-tag": self.refs[TAG] = T
            if body["ref"] in self.refs:
                raise HTTPError(request.full_url,422,"Reference already exists",{},None)
            self.refs[body["ref"]] = body["sha"]
            return self.response({"ref": body["ref"], "object": {"type": "tag", "sha": body["sha"]}})
        assert method == "POST" and path == "/graphql"
        updates = body["variables"]["input"]["refUpdates"]
        assert body["variables"]["input"]["repositoryId"] == "repository-node"
        if any(oid in self.targets for update in updates for oid in (update["beforeOid"], update["afterOid"])):
            return self.response({"errors": [{"type": "UNPROCESSABLE", "path": ["updateRefs"], "message": "Invalid object type tag, expected commit"}], "data": {"updateRefs": None}})
        if self.race == "branch": self.refs[BRANCH] = B
        if any(self.refs.get(update["name"],ZERO) != update["beforeOid"] for update in updates):
            return self.response({"errors": [{"type": "UNPROCESSABLE", "path": ["updateRefs"], "message": "ref changed"}], "data": {"updateRefs": None}})
        if self.result is not None: return self.response(self.result)
        for update in updates:
            if update["afterOid"] == ZERO: self.refs.pop(update["name"])
            else: self.refs[update["name"]] = update["afterOid"]
        if self.lost: raise TimeoutError("response lost after update")
        return self.response({"data": {"updateRefs": {"clientMutationId": body["variables"]["input"]["clientMutationId"]}}})
    @staticmethod
    def response(body): return BufferedResponse(json.dumps(body).encode(),{},200)
    def store(self): return GitHubRepoStore("org",lambda:"private-token",transport=GitHubTransport(opener=self.open))

@intent("INT-FC-R79")
@pytest.mark.parametrize("existing",[None,T])
def test_atomic_close_retains_tag_and_deletes_only_approved_branch(existing):
    host=Host(existing=existing)
    host.store().close_line("org/app",expected_revision=A)
    assert host.refs == {TAG:T}
    mutations=[call for call in host.calls if call[1]=="/graphql"]
    assert len(mutations)==1
    assert mutations[0][2]["variables"]["input"]["refUpdates"] == [{"name":BRANCH,"beforeOid":A,"afterOid":ZERO}]
    created=[call[2] for call in host.calls if call[1].endswith("/git/refs")]
    assert created == ([] if existing else [{"ref":TAG,"sha":T}])
    assert not any(call[0]=="DELETE" for call in host.calls)

@intent("INT-FC-R79")
@pytest.mark.parametrize("existing",[None,T])
def test_branch_advance_at_mutation_boundary_survives_atomic_rejection(existing):
    host=Host(existing=existing,race="branch")
    with pytest.raises(Conflict): host.store().close_line("org/app",expected_revision=A)
    # The branch that moved keeps its branch; the tag anchors the tip that was approved.
    assert host.refs[BRANCH]==B
    assert host.refs.get(TAG)==T
    assert len([call for call in host.calls if call[1]=="/graphql"])==1

@intent("INT-FC-R79")
def test_concurrent_tag_collision_preserves_both_refs():
    host=Host(race="tag")
    with pytest.raises(Conflict): host.store().close_line("org/app",expected_revision=A)
    assert host.refs == {BRANCH:A,TAG:OTHER}
    assert not any(call[1]=="/graphql" for call in host.calls)

@intent("INT-FC-R179")
def test_a_tag_another_close_created_on_the_same_tip_resumes_at_the_delete():
    host=Host(race="same-tag")
    host.store().close_line("org/app",expected_revision=A)
    assert host.refs == {TAG:T}

@intent("INT-FC-R179")
def test_a_tag_github_refuses_for_another_reason_stops_the_close_with_the_branch_kept():
    host=Host(race="ruleset")
    with pytest.raises(SourceUnavailable, match="refused the delivered tag"): host.store().close_line("org/app",expected_revision=A)
    assert host.refs == {BRANCH:A}
    assert not any(call[1]=="/graphql" for call in host.calls)

@intent("INT-FC-R179")
def test_the_tag_ref_never_rides_updaterefs_which_refuses_a_tag_object():
    """GitHub answers 'Invalid object type tag, expected commit' to a ref update carrying an
    annotated tag object, so the close that sent the tag through updateRefs never landed."""
    host=Host()
    host.store().close_line("org/app",expected_revision=A)
    sent=[update for call in host.calls if call[1]=="/graphql" for update in call[2]["variables"]["input"]["refUpdates"]]
    assert sent == [{"name":BRANCH,"beforeOid":A,"afterOid":ZERO}]
    assert host.refs == {TAG:T}

@intent("INT-FC-R79")
def test_existing_tag_collision_has_no_mutation():
    host=Host(existing=OTHER)
    with pytest.raises(ValueError): host.store().close_line("org/app",expected_revision=A)
    assert host.refs == {BRANCH:A,TAG:OTHER}
    assert all(method=="GET" for method,_,_ in host.calls)

@intent("INT-FC-R79")
@pytest.mark.parametrize("result",[{}, {"data":{"updateRefs":None}}, {"data":{"updateRefs":{"clientMutationId":"wrong"}}}])
def test_unconfirmed_graphql_result_never_returns_success(result):
    host=Host(result=result)
    with pytest.raises(SourceUnavailable): host.store().close_line("org/app",expected_revision=A)
    assert host.refs=={BRANCH:A,TAG:T}

@intent("INT-FC-R79")
def test_lost_atomic_response_is_not_retried_and_history_remains_anchored():
    host=Host(lost=True)
    with pytest.raises(SourceUnavailable): host.store().close_line("org/app",expected_revision=A)
    assert host.refs=={TAG:T}
    assert len([call for call in host.calls if call[1]=="/graphql"])==1


@intent("INT-FC-R79")
def test_lost_atomic_response_remains_durable_unknown_after_restart(tmp_path):
    from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
    from orchestrator.application.services.operations.operation_admission import OperationAdmission
    from orchestrator.domain.model.command_context import CommandContext
    from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
    host=Host(lost=True)
    store=host.store()
    context=CommandContext("operator","local","grant",frozenset({"delivery.close"}),frozenset({"org/app"}),"revision","org")
    def execute():
        admission=OperationAdmission(OperationReceiptStore(tmp_path))
        return admission.execute(context,"delivery.close","org/app","same-operation",{"expected_revision":A},lambda:store.close_line("org/app",expected_revision=A))
    with pytest.raises(OperationUnknown): execute()
    count=len(host.calls)
    with pytest.raises(OperationUnknown): execute()
    assert len(host.calls)==count
    assert host.refs=={TAG:T}
    assert len([call for call in host.calls if call[1]=="/graphql"])==1
