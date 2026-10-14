"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

import logging
from functools import partial

from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.runs.run_graph import RunGraphPort
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.execution.workflow_compiler import (
    WorkflowCompiler,
)
from orchestrator.application.ports.outbound.maintenance_acts import MaintenanceActs
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.definitions import _RECEIPT_TICKS
from orchestrator.application.services.maintenance.derive_oneshot_ledger import (
    helper_derive_oneshot_ledger,
)
from orchestrator.application.services.maintenance.judge_one_drive import (
    helper_judge_one_drive,
)
from orchestrator.application.services.runs.list_run_rows import helper_list_run_rows
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def helper_judge_oneshot_runs(
    runs: list[RunInventoryEntry] | None = None,
    *,
    observations: ObservationStore,
    config: ConfigStore | None,
    credentials: CredentialStore | None,
    door: Door | None,
    events: EventPublisher | None,
    macts: MaintenanceActs | None,
    msource: MaintenanceSource | None,
    psource: PromotionSource | None,
    studios: StudioGateway | None,
    worker_image: str,
    workflows: WorkflowRunner | None,
    cap_delivery_config: DeliveryConfigPort,
    cap_git_roles: GitRolesPort,
    cap_instantiation: InstantiationPort,
    cap_list_git_identities: ListGitIdentitiesPort,
    cap_pair_credential_held: PairCredentialHeldPort,
    cap_run_graph: RunGraphPort,
    cap_run_retention: RunRetentionPort,
    compiler: WorkflowCompiler,
    context: CommandContext,
) -> None:
    """The engine's gate over finished one-shot drives: read the verdict from GitHub
    (never from worker output) and act deterministically - merge on PASS + green
    checks (INT-FC-R65), re-drive on a FAIL while the attempt budget holds
    (INT-FC-R75), park everything else. No agent ever merges. The caller passes the
    run rows when it already holds them, so one refresh tick reads the executor once."""
    if runs is None:
        runs = partial(helper_list_run_rows, workflows=workflows)()
    partial(
        helper_derive_oneshot_ledger, observations=observations, workflows=workflows
    )(runs)
    if (
        not observations.oneshot
        or workflows is None
        or msource is None
        or (macts is None)
    ):
        return
    for handle, entry in list(observations.oneshot.items()):
        if entry.get("acted"):
            entry["settled"] = entry.get("settled", 0) + 1
            if entry["settled"] > _RECEIPT_TICKS:
                observations.oneshot.pop(handle, None)
            continue
        try:
            partial(
                helper_judge_one_drive,
                observations=observations,
                config=config,
                credentials=credentials,
                door=door,
                events=events,
                macts=macts,
                msource=msource,
                psource=psource,
                studios=studios,
                worker_image=worker_image,
                workflows=workflows,
                cap_delivery_config=cap_delivery_config,
                cap_git_roles=cap_git_roles,
                cap_instantiation=cap_instantiation,
                cap_list_git_identities=cap_list_git_identities,
                cap_pair_credential_held=cap_pair_credential_held,
                cap_run_graph=cap_run_graph,
                cap_run_retention=cap_run_retention,
                compiler=compiler,
                context=context,
            )(handle, entry, runs)
        except (OperationUnknown, PermissionDenied):
            raise
        except Exception:
            logging.getLogger(__name__).warning(
                "Independent observation failed", exc_info=True
            )
            continue
