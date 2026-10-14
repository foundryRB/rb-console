"""Execution spec compiler boundary for authorized commands."""

from __future__ import annotations

from typing import Protocol

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


class WorkflowCompiler(Protocol):
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
    ) -> CompiledWorkflow: ...

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
    ) -> CompiledWorkflow: ...

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
    ) -> CompiledWorkflow: ...
