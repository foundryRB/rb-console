"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.maintenance_resolver import (
    checks_state,
    pr_resolves_ticket,
)
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
from orchestrator.application.services.events.narrate_park import helper_narrate_park
from orchestrator.application.services.maintenance.act_on_verdict import (
    helper_act_on_verdict,
)
from orchestrator.application.services.maintenance.judge_managed_drive import (
    helper_judge_managed_drive,
)
from orchestrator.application.services.maintenance.merger import helper_merger
from orchestrator.application.services.maintenance.verdict import decide
from orchestrator.application.services.promotion.home_target import helper_home_target
from orchestrator.application.services.runs.terminal_exit_of import (
    helper_terminal_exit_of,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.run_policy import stop_name


def helper_judge_one_drive(
    handle: str,
    entry: dict,
    runs: list[RunInventoryEntry],
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
    """Judge ONE finished drive. Isolated per entry so an unreadable one (a GitHub read
    that raises mid-sweep) is retried next tick rather than stranding every entry behind
    it un-judged - which reads on the panel as a drive that runs forever."""
    phase = workflows.status(handle)
    if phase in ("Running", "Pending", "Suspended"):
        return
    if phase != "Succeeded":
        entry["acted"] = True
        stop = stop_name(
            partial(helper_terminal_exit_of, cap_run_graph=cap_run_graph)(handle)
        )
        entry["result"] = f"parked: {stop} stop" if stop else f"parked: run {phase}"
        partial(helper_narrate_park, events=events)(
            repo_ticket=entry, handle=handle, reason=entry["result"]
        )
        return
    repo, ticket = (entry["repo"], entry["ticket"])
    home = partial(
        helper_home_target, psource=psource, cap_instantiation=cap_instantiation
    )(repo)
    if home is not None:
        partial(
            helper_judge_managed_drive,
            observations=observations,
            config=config,
            credentials=credentials,
            door=door,
            events=events,
            macts=macts,
            msource=msource,
            studios=studios,
            worker_image=worker_image,
            workflows=workflows,
            cap_delivery_config=cap_delivery_config,
            cap_git_roles=cap_git_roles,
            cap_pair_credential_held=cap_pair_credential_held,
            cap_run_retention=cap_run_retention,
            compiler=compiler,
            context=context,
        )(handle, entry, runs, home)
        return
    prs = msource.open_prs(repo)

    def _is_driven(p: MaintenancePullRequest) -> bool:
        return pr_resolves_ticket(
            p.head_branch or "",
            p.title,
            p.body or "",
            ticket,
        )

    pr = next((p for p in prs if _is_driven(p)), None)
    if pr is None:
        closed = msource.closed_prs(repo)
        done = next(
            (
                c
                for c in closed
                if c.merged
                and pr_resolves_ticket(
                    c.head_branch or "",
                    c.title,
                    c.body or "",
                    ticket,
                )
            ),
            None,
        )
        entry["acted"] = True
        entry["result"] = (
            f"already merged PR #{done.number}"
            if done
            else "parked: no open PR carries the ticket"
        )
        if not done:
            partial(helper_narrate_park, events=events)(
                repo_ticket=entry, handle=handle, reason=entry["result"]
            )
        return
    author = pr.author or ""
    number = pr.number
    verdict, findings = decide(
        msource.pr_reviews(repo, number),
        author,
        partial(
            helper_merger,
            cap_git_roles=cap_git_roles,
            cap_list_git_identities=cap_list_git_identities,
        )(),
    )
    checks = checks_state(msource.check_runs(repo, pr.head_sha or ""))
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
        pr_repo=repo,
        number=number,
        verdict=verdict,
        checks=checks,
        findings=findings,
        home=None,
    )
