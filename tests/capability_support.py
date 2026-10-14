"""Explicit ports and authority doubles for business rule unit tests."""
from __future__ import annotations
from orchestrator.domain.model.repository_file import RepositoryFile

import importlib
import inspect
import tempfile
from dataclasses import fields
from pathlib import Path
from uuid import uuid4

from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from orchestrator.adapters.outbound.memory.index import DeliveryIndex
from orchestrator.adapters.outbound.records.lifecycle_codec import encode_pin
from orchestrator.application.ports.inbound.command_actions import COMMAND_ACTIONS
from orchestrator.application.services.operations.operation_admission import OperationAdmission
from orchestrator.container import build_capabilities
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.repository_identity import RepositoryIdentity
from orchestrator.domain.delivery import delivery_slug


class UnitCommandContext(CommandContext):
    def repository_id(self, repository: str) -> str:
        return str(repository).lower()


def command_kwargs(repository: str = "") -> dict:
    return {
        "context": UnitCommandContext("unit-operator", "local", "unit-grant",
                                      frozenset(COMMAND_ACTIONS.values()), frozenset({str(repository).lower()}),
                                      "unit-authorization", "unit-installation", admin=True),
        "operation_id": uuid4().hex,
    }


class LocalTestSource:
    def __init__(self, repos) -> None:
        self.repos = repos

    def state_of(self, repo: str):
        return derive_state(repo)

    def list_org_repos(self):
        return []

    def scan(self):
        repos = set(self.repos.list_delivery_repos())
        for repo in list(repos):
            path = Path(repo)
            if path.is_dir():
                repos.update(str(scratch.parent) for scratch in path.rglob(".delivery") if scratch.is_dir())
        return [derive_state(repo) for repo in repos]

    def content_revision(self, repo: str, path: str = '') -> str:
        from hashlib import sha256
        target = Path(repo) / path
        return sha256(target.read_bytes() if target.is_file() else b'').hexdigest()

    def file(self, repo: str, path: str, *, revision: str = '') -> dict:
        target = Path(repo) / path
        content = target.read_text(encoding='utf-8') if target.is_file() else ''
        return RepositoryFile(path, content, len(content.encode()))

    def read_config(self, repo: str, *, revision: str = "") -> dict:
        import json
        path = Path(repo) / ".delivery" / "config.json"
        return json.loads(path.read_text()) if path.is_file() else {}


class TestRepositoryIncarnations:
    __test__ = False
    def __init__(self, repos=None):
        self.repos = repos

    def verify_current(self, repo: str) -> RepositoryIdentity:
        return RepositoryIdentity("unit-org/" + delivery_slug(repo), "1")

    def observe(self, repo: str) -> RepositoryIdentity | None:
        if Path(repo).is_dir() or (self.repos is not None and hasattr(self.repos, "repo_exists") and self.repos.repo_exists(repo)):
            return RepositoryIdentity("unit-org/" + delivery_slug(repo), "1")
        return None

    def reconcile(self, repo: str, before: RepositoryIdentity | None) -> RepositoryIdentity:
        return RepositoryIdentity("unit-org/" + delivery_slug(repo), "1")

    def adopt(self, repo: str) -> RepositoryIdentity:
        return RepositoryIdentity("unit-org/" + delivery_slug(repo), "1")


class UnitPinnedSource:
    """Explicit current-runtime provenance for business-rule source fixtures."""
    def __init__(self, source, image):
        self.source, self.image = source, image
    def _pin(self, state):
        from dataclasses import replace
        from orchestrator.domain.current_lifecycle import CURRENT_PLAYBOOK_REF
        definition = replace(state.lifecycle, source_ref=CURRENT_PLAYBOOK_REF, worker_image=self.image)
        return replace(state, lifecycle=definition)
    def state_of(self, repo):
        return self._pin(self.source.state_of(repo))
    def scan(self):
        return [self._pin(state) for state in self.source.scan()]
    def read_config(self, repo, *, revision=''):
        return self.source.read_config(repo, revision=revision)
    def list_org_repos(self):
        return self.source.list_org_repos()
    def content_revision(self, repo, path=''):
        return self.source.content_revision(repo, path)
    def file(self, repo, path, *, revision=''):
        return self.source.file(repo, path, revision=revision)
    def tree(self, repo, *, revision='', scratch_revision=''):
        return self.source.tree(repo, revision=revision, scratch_revision=scratch_revision)
    def present_records(self, repo):
        return self.source.present_records(repo)

class UnitCredentials:
    def __init__(self):
        self.values = {}
    def has_delivery(self, slug):
        return slug in self.values
    def delivery_ref(self, slug):
        return 'fixture-delivery-' + slug
    def put_delivery(self, slug, value):
        self.values[slug] = value
        return self.delivery_ref(slug)
    def delete_delivery(self, slug):
        self.values.pop(slug, None)
    def run_ref(self, run_id):
        return 'fixture-run-' + run_id
    def put(self, run_id, value):
        return self.run_ref(run_id)
    def delete(self, run_id):
        return None


class TestWorkerStudio:
    def agent_catalog(self):
        from orchestrator.domain.model.catalog_agent import CatalogAgent
        return [CatalogAgent(name, name, '', (), (), 'auto', True, name == 'reviewer', '') for name in ('programmer', 'reviewer', 'librarian', 'release-manager')]
    def health(self):
        return []
    def artifacts_for(self, slug):
        return {}
    def platform_apps(self):
        return []
    def estimatekit_slugs(self):
        return []
    def protopane_slugs(self):
        return []
    def playbook_repo(self):
        return ''

class TestPromotionSource:
    def repository_revision(self, repo: str) -> str:
        return 'unit-head'
    def contract_text(self, repo: str, *, revision: str = '') -> str:
        return ''
    def deploy_installs(self, repo: str) -> dict:
        return {"unit": ["test"]}


def make_capabilities(*args, **kwargs):
    kwargs.setdefault('worker_image', 'worker:1.0.0')
    from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
    kwargs.setdefault('config', InMemoryConfigStore())
    kwargs.setdefault('credentials', UnitCredentials())
    kwargs.setdefault("admission", OperationAdmission(OperationReceiptStore(tempfile.mkdtemp(prefix="console-unit-"))))
    kwargs.setdefault("incarnations", TestRepositoryIncarnations(args[0] if args else None))
    kwargs.setdefault("psource", TestPromotionSource())
    if kwargs.get("msource") is not None and kwargs.get("credentials") is not None:
        kwargs.setdefault("studios", TestWorkerStudio())
        settings = kwargs.get("config")
        if settings is not None and settings.__class__.__name__ == "InMemoryConfigStore":
            from orchestrator.application.services.definitions import _GIT_ROLES, _GITID
            if not any(k != "configured" for k in settings.get_setting(_GIT_ROLES)):
                settings.put_setting(_GIT_ROLES, {name: "unit-worker" for name in ("programmer", "reviewer", "librarian", "release-manager")}, None)
                settings.put_setting(_GITID + "unit-worker", {"name": "unit-worker", "email": "unit@fixture"}, "unit-token")
    kwargs.setdefault("run_log_store", FileRunLogStore(tempfile.mkdtemp(prefix="console-archive-unit-")))
    if kwargs.get("source") is None and args:
        source = LocalTestSource(args[0])
        kwargs["source"] = source
        index = kwargs.setdefault("index", DeliveryIndex())
        if hasattr(args[0], "list_delivery_repos"):
            for state in source.scan():
                index.put(state)
    if kwargs.get('source') is not None:
        kwargs['source'] = UnitPinnedSource(kwargs['source'], kwargs['worker_image'])
    return build_capabilities(*args, **kwargs)


def invoke_helper(capabilities, name: str, *args, **kwargs):
    root = Path(__file__).parent.parent / "orchestrator" / "application" / "services"
    candidates = list(root.glob("*/" + name.lstrip("_") + ".py"))
    if len(candidates) != 1:
        raise AssertionError(f"Helper has no unique owner: {name}")
    module = ".".join(candidates[0].relative_to(root.parent.parent.parent).with_suffix("").parts)
    helper = getattr(importlib.import_module(module), "helper" + name)
    for param in inspect.signature(helper).parameters.values():
        if param.kind != inspect.Parameter.KEYWORD_ONLY or param.name in kwargs:
            continue
        if param.name == 'context':
            kwargs[param.name] = UnitCommandContext('unit-operator', 'local', 'unit-grant', frozenset({*COMMAND_ACTIONS.values(), 'maintenance.reconcile'}), frozenset({'org/*', 'example-org/*'}), 'unit-authorization', 'unit-installation', admin=True)
            continue
        if param.name.startswith("cap_"):
            kwargs[param.name] = getattr(capabilities, param.name.removeprefix("cap_"))
            continue
        candidates = [getattr(getattr(capabilities, field.name), param.name)
                      for field in fields(capabilities)
                      if hasattr(getattr(capabilities, field.name), param.name)]
        if not candidates:
            raise AssertionError(f"No test dependency supplied for {name}.{param.name}")
        kwargs[param.name] = candidates[0]
    return helper(*args, **kwargs)


def with_lifecycle(config: dict, lifecycle) -> dict:
    """The configuration a repository store persists, with the captured definition it is handed."""
    if lifecycle is None:
        return config
    return {**config, "lifecycle": encode_pin(lifecycle)}


def observe_repo(capabilities, repo: str):
    """Publish an explicit source observation before testing projection views."""
    collector = capabilities.refresh.cap_refresh_metadata
    values = collector.observations.metadata.setdefault(repo, {})
    values['maintenance_state'] = collector.maintenance.execute(repo)
    return capabilities
