"""Compile application execution specifications into opaque Argo input."""

from __future__ import annotations

import json
from dataclasses import asdict

from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.adapters.outbound.argo.maintenance_launch import (
    compile_maintenance_workflow,
)
from orchestrator.adapters.outbound.argo.promotion_launch import (
    compile_promotion_workflow,
)
from orchestrator.adapters.outbound.argo.retention import gc_policy
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.demo_source import DemoSource
from orchestrator.domain.model.git_identity import GitIdentity
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.pair_credential import PairCredential
from orchestrator.domain.model.pair_home import PairHome
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_retention import RunRetention


def _execution(
    repo: str, run_id: str, payload: dict, source_revision: str | None = None
) -> CompiledWorkflow:
    payload["metadata"].pop("generateName", None)
    payload["metadata"]["name"] = run_id
    if source_revision is not None:
        payload["metadata"].setdefault("annotations", {})[
            "foundry-console/source-revision"
        ] = source_revision
    return CompiledWorkflow(run_id, run_id, repo, json.dumps(payload, sort_keys=True))


class ArgoWorkflowCompiler:
    def __init__(self, *, public_domain: str = "") -> None:
        self._public_domain = public_domain

    def compile_delivery(
        self,
        repo: str,
        state: DeliveryState,
        config: RunConfig,
        *,
        run_id: str,
        credential_secret: str = "",
        from_phase: str | None = None,
        feedback: str = "",
        worker_image: str = "",
        namespace: str = "foundry-console",
        service_account: str = "foundry-console-worker",
        max_attempts: int = 3,
        deadline_seconds: int = 3600,
        git_identities: dict[str, GitIdentity] | None = None,
        retention: RunRetention | None = None,
        home: PairHome | None = None,
        catalog: dict[str, CatalogAgent] | None = None,
        tool_urls: dict[str, str] | None = None,
        demo: DemoSource | None = None,
        definition: LifecycleDefinition | None = None,
        playbook_ref: str = "",
    ) -> CompiledWorkflow:
        payload = compile_workflow(
            repo=repo,
            state=state,
            config=config,
            run_id=run_id,
            credential_secret=credential_secret,
            from_phase=from_phase,
            feedback=feedback,
            worker_image=worker_image,
            public_domain=self._public_domain,
            namespace=namespace,
            service_account=service_account,
            max_attempts=max_attempts,
            deadline_seconds=deadline_seconds,
            git_identities=git_identities,
            home=home,
            catalog=catalog,
            tool_urls=tool_urls,
            demo=demo,
            definition=definition,
            playbook_ref=playbook_ref,
            gc=gc_policy(**asdict(retention)) if retention else None,
        )
        return _execution(repo, run_id, payload)

    def compile_maintenance(
        self,
        repo: str,
        act: str,
        target: int | None,
        mode: MaintenanceMode,
        config: RunConfig,
        *,
        run_id: str,
        source_revision: str = "",
        credential_secret: str = "",
        feedback: str = "",
        worker_image: str = "",
        namespace: str = "foundry-console",
        service_account: str = "foundry-console-worker",
        retention: RunRetention | None = None,
        max_attempts: int = 3,
        deadline_seconds: int = 1800,
        git_identities: dict[str, GitIdentity] | None = None,
        home: PairHome | None = None,
        catalog: dict[str, CatalogAgent] | None = None,
    ) -> CompiledWorkflow:
        payload = compile_maintenance_workflow(
            repo=repo,
            act=act,
            target=target,
            mode=mode,
            config=config,
            run_id=run_id,
            source_revision=source_revision,
            credential_secret=credential_secret,
            feedback=feedback,
            worker_image=worker_image,
            public_domain=self._public_domain,
            namespace=namespace,
            service_account=service_account,
            max_attempts=max_attempts,
            deadline_seconds=deadline_seconds,
            git_identities=git_identities,
            home=home,
            catalog=catalog,
            gc=gc_policy(**asdict(retention)) if retention else None,
        )
        return _execution(repo, run_id, payload, source_revision)

    def compile_promotion(
        self,
        repo: str,
        target: PromotionTarget,
        release: str,
        config: RunConfig,
        *,
        run_id: str,
        source_revision: str = "",
        credential_secret: str = "",
        pair: PairCredential | None = None,
        git_identity: GitIdentity | None = None,
        catalog: dict[str, CatalogAgent] | None = None,
        worker_image: str = "",
        namespace: str = "foundry-console",
        service_account: str = "foundry-console-worker",
        retention: RunRetention | None = None,
        max_attempts: int = 3,
        deadline_seconds: int = 1800,
    ) -> CompiledWorkflow:
        payload = compile_promotion_workflow(
            repo=repo,
            target=target,
            release=release,
            config=config,
            run_id=run_id,
            source_revision=source_revision,
            credential_secret=credential_secret,
            pair=pair,
            git_identity=git_identity,
            catalog=catalog,
            worker_image=worker_image,
            public_domain=self._public_domain,
            namespace=namespace,
            service_account=service_account,
            max_attempts=max_attempts,
            deadline_seconds=deadline_seconds,
            gc=gc_policy(**asdict(retention)) if retention else None,
        )
        return _execution(repo, run_id, payload, source_revision)
