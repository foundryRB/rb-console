"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.maintenance_resolver import checks_state
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
from orchestrator.application.services.events.narrate_park import helper_narrate_park
from orchestrator.application.services.maintenance.act_on_verdict import (
    helper_act_on_verdict,
)
from orchestrator.application.services.maintenance.verdict import decide
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.repository_door import home_pr_from_comments


def helper_judge_managed_drive(
    handle: str,
    entry: dict,
    runs: list[RunInventoryEntry],
    home: PromotionTarget,
    *,
    observations: ObservationStore,
    config: ConfigStore | None,
    credentials: CredentialStore | None,
    door: Door | None,
    events: EventPublisher | None,
    macts: MaintenanceActs | None,
    msource: MaintenanceSource | None,
    studios: StudioGateway | None,
    worker_image: str,
    workflows: WorkflowRunner | None,
    cap_delivery_config: DeliveryConfigPort,
    cap_git_roles: GitRolesPort,
    cap_pair_credential_held: PairCredentialHeldPort,
    cap_run_retention: RunRetentionPort,
    compiler: WorkflowCompiler,
    context: CommandContext,
) -> None:
    """Judge ONE finished one-shot drive over a MANAGED app. The pull request is on the
    home, so it is found through the ONE pointer the resolve recorded on our ticket and
    read on the pair's credential (INT-FC-R135), never by listing theirs; its verdict and
    checks are then judged by the same rules as any other drive, and the one act the
    engine withholds is the merge, which is theirs (INT-FC-R132). A FAIL re-drives on
    the findings, carrying the home, exactly as over an app we hold."""
    repo, ticket = (entry["repo"], entry["ticket"])

    def park(reason: str) -> None:
        entry["acted"] = True
        entry["result"] = reason
        partial(helper_narrate_park, events=events)(
            repo_ticket=entry, handle=handle, reason=reason
        )

    if door is None or msource is None:
        park(f"parked: no door to read {home.repo}, so the home PR cannot be judged")
        return
    pointer = home_pr_from_comments(msource.issue_comments(repo, ticket))
    if pointer is None:
        park(
            f"parked: no home PR recorded on #{ticket} (the resolve left no pointer to {home.repo})"
        )
        return
    home_repo, number = pointer
    pr = door.pull_request(home_repo, number, home.credential)
    if not pr:
        park(f"parked: {home_repo}#{number} could not be read on the pair's credential")
        return
    if (pr.state or "").lower() != "open":
        if pr.merged:
            entry["acted"] = True
            entry["result"] = f"already merged {home_repo}#{number} (theirs)"
        else:
            park(f"parked: {home_repo}#{number} is closed unmerged")
        return
    author = pr.author or ""
    verdict, findings = decide(pr.reviews or [], author)
    partial(
        helper_act_on_verdict,
        msource=msource,
        door=door,
        observations=observations,
        config=config,
        credentials=credentials,
        events=events,
        macts=macts,
        studios=studios,
        worker_image=worker_image,
        workflows=workflows,
        cap_delivery_config=cap_delivery_config,
        cap_git_roles=cap_git_roles,
        cap_pair_credential_held=cap_pair_credential_held,
        cap_run_retention=cap_run_retention,
        compiler=compiler,
        context=context,
    )(
        handle,
        entry,
        runs,
        pr_repo=home_repo,
        number=number,
        verdict=verdict,
        checks=checks_state(pr.checks or []),
        findings=findings,
        home=home,
    )
