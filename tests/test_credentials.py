"""The credential store: drive persists the credential per delivery (a namespace Secret by
slug), and the compiled workflow references it by that ref, never inlining the value."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
from dataclasses import replace
from pytest_intent import intent
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from capability_support import make_capabilities
from orchestrator.domain.model.run_config import RunConfig

class FakeRepos:

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        return target

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class RefSource:
    """state_of over the local scratch with the line's ref attached, the way the remote
    source resolves it (the compiler refuses a delivery run without a scratch ref)."""

    def scan(self):
        return []

    def state_of(self, repo):
        return replace(derive_state(repo), scratch_ref='delivery/2026-08-18')

    def read_config(self, repo, *, revision=""):
        return {}

    def present_records(self, repo):
        return []

class FakeCredentials:

    def __init__(self):
        self.stored: dict[str, str] = {}

    def put_delivery(self, slug, credential):
        self.stored[slug] = credential
        return f'fc-delivery-{slug}'

    def has_delivery(self, slug):
        return slug in self.stored

    def get_delivery(self, slug):
        return self.stored.get(slug, '')

    def delivery_ref(self, slug):
        return f'fc-delivery-{slug}'

@intent('INT-FC-R26')
def test_drive_stores_the_credential_by_delivery_and_references_it(tmp_path):
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    creds = FakeCredentials()
    service = make_capabilities(FakeRepos(), credentials=creds, source=RefSource())
    result = service.drive.execute((_command_repository := str(tmp_path / 'acme')), RunConfig('tok', 'acme', True), run_id='r9', **command_kwargs(_command_repository))
    assert creds.stored == {'acme': 'tok'}
    blob = str(result.workflow)
    assert 'fc-delivery-acme' in blob
    assert 'tok' not in blob
