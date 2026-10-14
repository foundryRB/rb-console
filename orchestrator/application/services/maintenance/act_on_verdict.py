"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.events import PR_JUDGED, PR_MERGED, state_fact
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
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
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.definitions import _CHECKS_TICKS
from orchestrator.application.services.events.narrate_park import helper_narrate_park
from orchestrator.application.services.maintenance.redrive_oneshot import (
    helper_redrive_oneshot,
)
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.maintenance import CHECKS_PENDING, VERDICT_FAIL
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.merge_gate import MergeGate
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.resolve_retry import ResolveRetry
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.maintenance_judge import (
    judge_one_shot,
    judge_resolve_fail,
)


def helper_act_on_verdict(
    handle: str,
    entry: dict,
    runs: list[RunInventoryEntry],
    *,
    pr_repo: str,
    number: int,
    verdict: str,
    checks: str,
    findings: str,
    home: PromotionTarget | None,
    observations: ObservationStore,
    config: ConfigStore | None,
    credentials: CredentialStore | None,
    events: EventPublisher | None,
    macts: MaintenanceActs | None,
    studios: StudioGateway | None,
    worker_image: str,
    workflows: WorkflowRunner | None,
    cap_delivery_config: DeliveryConfigPort,
    cap_git_roles: GitRolesPort,
    cap_pair_credential_held: PairCredentialHeldPort,
    cap_run_retention: RunRetentionPort,
    compiler: WorkflowCompiler,
    context: CommandContext,
    msource: MaintenanceSource | None,
    door: Door | None,
) -> None:
    """The engine's one act over a judged pull request, wherever it lives: merge on a
    PASS with green checks (INT-FC-R65) - withheld over a home, whose merge is theirs
    (INT-FC-R132) - re-drive on a FAIL while the budget holds (INT-FC-R75), wait on
    pending checks, park everything else. ``pr_repo`` is where the PR is (ours, or the
    home), ``findings`` the body of the review that decided the verdict, so a re-drive
    threads the findings the verdict was judged on."""
    repo, ticket = (entry["repo"], entry["ticket"])
    label = f"PR #{number}" if pr_repo == repo else f"{pr_repo}#{number}"
    judged = judge_one_shot(verdict, checks)
    state_fact(
        events,
        event_type=PR_JUDGED,
        subject=repo,
        data={
            "repo": repo,
            "pr": number,
            "pr_repo": pr_repo,
            "ticket": ticket,
            "verdict": verdict,
            "checks": checks,
            "gate": judged.value,
        },
    )
    if judged is MergeGate.MERGE:
        if home is not None:
            entry["acted"] = True
            entry["result"] = (
                f"proven: {label} carries a recorded PASS on green checks - theirs to merge"
            )
            partial(helper_narrate_park, events=events)(
                repo_ticket=entry, handle=handle, reason=entry["result"]
            )
            return
        try:
            macts.merge(repo, number)
            entry["result"] = f"merged PR #{number} on the recorded PASS"
            state_fact(
                events,
                event_type=PR_MERGED,
                subject=repo,
                data={"repo": repo, "pr": number, "ticket": ticket, "by": "judge"},
            )
        except (OperationUnknown, PermissionDenied):
            raise
        except Exception as exc:  # noqa: BLE001 - publish the visible refusal
            entry["result"] = f"parked: merge refused ({exc})"
            partial(helper_narrate_park, events=events)(
                repo_ticket=entry, handle=handle, reason=entry["result"]
            )
        entry["acted"] = True
    elif verdict == VERDICT_FAIL:
        attempts = sum(
            1
            for r in runs
            if r.maintenance_act == "resolve"
            and r.mode == "one-shot"
            and r.repository == repo
            and r.kind == "maintenance"
            and (str(r.ticket or "") == str(ticket))
        )
        if judge_resolve_fail(attempts) is ResolveRetry.RETRY:
            partial(
                helper_redrive_oneshot,
                observations=observations,
                config=config,
                credentials=credentials,
                studios=studios,
                worker_image=worker_image,
                workflows=workflows,
                cap_delivery_config=cap_delivery_config,
                cap_git_roles=cap_git_roles,
                cap_pair_credential_held=cap_pair_credential_held,
                cap_run_retention=cap_run_retention,
                compiler=compiler,
                context=context,
                msource=msource,
                door=door,
            )(
                handle,
                entry,
                repo,
                ticket,
                number,
                attempts,
                findings=findings,
                home=home,
            )
        else:
            entry["acted"] = True
            entry["result"] = (
                f"degraded: {label} still FAILs after {attempts} attempts - over to you"
            )
            partial(helper_narrate_park, events=events)(
                repo_ticket=entry, handle=handle, reason=entry["result"]
            )
    elif checks == CHECKS_PENDING and entry["ticks"] < _CHECKS_TICKS:
        entry["ticks"] += 1
        entry["result"] = f"{label} open - the merge gate waits on its checks"
    else:
        entry["acted"] = True
        entry["result"] = f"parked: {label} verdict {verdict}, checks {checks}"
        partial(helper_narrate_park, events=events)(
            repo_ticket=entry, handle=handle, reason=entry["result"]
        )
