from io import BytesIO
import pytest
from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource
from orchestrator.adapters.outbound.github.github_promotion_source import GithubPromotionSource
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from urllib.error import HTTPError

def error(status): return HTTPError("https://api.github.com/fault",status,"fault",{},BytesIO())

@pytest.mark.parametrize("status",[500,409])
def test_delivery_source_http_fault_is_never_absent(monkeypatch,status):
    source=GitHubDeliverySource("org",lambda:"token")
    monkeypatch.setattr(source,"_get",lambda *args: (_ for _ in ()).throw(error(status)))
    with pytest.raises(SourceUnavailable): source.state_of("app")

def test_confirmed_absent_repository_has_no_line(monkeypatch):
    source=GitHubDeliverySource("org",lambda:"token")
    monkeypatch.setattr(source,"_get",lambda *args: (_ for _ in ()).throw(error(404)))
    assert not source.state_of("app").exists

@pytest.mark.parametrize("payload",[{},None,["bad-row"]])
def test_malformed_ref_inventory_cannot_claim_empty(monkeypatch,payload):
    source=GitHubDeliverySource("org",lambda:"token")
    monkeypatch.setattr(source,"_get",lambda *args:payload)
    with pytest.raises(SourceUnavailable): source.state_of("app")

@pytest.mark.parametrize("payload",[{},[],{"encoding":"base64"}])
def test_malformed_promotion_file_is_unavailable(monkeypatch,payload):
    source=GithubPromotionSource("org",lambda:"token")
    monkeypatch.setattr(source,"_get",lambda *args:payload)
    with pytest.raises(SourceUnavailable): source.contract_text("app")

def test_confirmed_absent_promotion_contract_remains_absent(monkeypatch):
    source=GithubPromotionSource("org",lambda:"token")
    monkeypatch.setattr(source,"_get",lambda *args: (_ for _ in ()).throw(error(404)))
    assert source.contract_text("app") is None

@pytest.mark.parametrize("operation",["gitignore","journal","config","file","ensure"])
def test_failed_precondition_read_performs_no_write(monkeypatch,operation):
    store=GitHubRepoStore("org",lambda:"token")
    calls=[]
    def request(method,path,token,*args):
        calls.append((method,path))
        raise error(500)
    monkeypatch.setattr(store,"_req",request)
    monkeypatch.setattr(store,"_require_line_ref",lambda *args:"delivery/line")
    with pytest.raises(SourceUnavailable):
        if operation=="gitignore": store._ensure_scratch_ignored("org/app","token")
        elif operation=="journal": store.append_journal("org/app","entry")
        elif operation=="config": store.write_config("org/app",{})
        elif operation=="file": store._put_scratch_file("org/app","proposal.md","text","message","token","delivery/line")
        else: store.ensure("app")
    assert len(calls)==1 and calls[0][0]=="GET"

def test_malformed_repository_identity_does_not_trigger_create(monkeypatch):
    store=GitHubRepoStore("org",lambda:"token")
    calls=[]
    def request(method,path,token,*args): calls.append(method); return {}
    monkeypatch.setattr(store,"_req",request)
    with pytest.raises(SourceUnavailable): store.ensure("app")
    assert calls==["GET"]

@pytest.mark.parametrize("content",["!!!!", "//8="])
def test_corrupt_journal_bytes_perform_no_write(monkeypatch,content):
    store=GitHubRepoStore("org",lambda:"token")
    calls=[]
    def request(method,path,token,*args): calls.append(method); return {"content":content,"sha":"blob"}
    monkeypatch.setattr(store,"_req",request)
    monkeypatch.setattr(store,"_require_line_ref",lambda *args:"delivery/line")
    with pytest.raises(SourceUnavailable): store.append_journal("org/app","entry")
    assert calls==["GET"]
