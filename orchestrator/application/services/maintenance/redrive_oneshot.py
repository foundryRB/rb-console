"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial
from hashlib import sha256

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
from orchestrator.application.ports.outbound.execution.workflow_compiler import (
    WorkflowCompiler,
)
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.maintenance.track_oneshot import (
    helper_track_oneshot,
)
from orchestrator.application.services.promotion.pair_home import helper_pair_home
from orchestrator.application.services.runs.retention_gc import helper_retention_gc
from orchestrator.application.services.settings.git_identities_map import (
    helper_git_identities_map,
)
from orchestrator.application.services.settings.has_delivery_cred import (
    helper_has_delivery_cred,
)
from orchestrator.application.services.settings.with_delivery_config import (
    helper_with_delivery_config,
)
from orchestrator.application.services.studios.agent_catalog import helper_agent_catalog
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.exceptions.seat_refused import SeatRefused
from orchestrator.domain.services.agent_access import refuse_foreign_seat
from orchestrator.application.services.settings.target_selection import (
    helper_target_selection,
)
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.services.maintenance_judge import MAX_RESOLVE_ATTEMPTS


def helper_redrive_oneshot(
    old_handle: str,
    entry: dict,
    repo: str,
    ticket: int,
    number: int,
    attempts: int,
    findings: str = "",
    home: PromotionTarget | None = None,
    *,
    observations: ObservationStore,
    config: ConfigStore | None,
    credentials: CredentialStore | None,
    studios: StudioGateway | None,
    worker_image: str,
    workflows: WorkflowRunner | None,
    cap_delivery_config: DeliveryConfigPort,
    cap_git_roles: GitRolesPort,
    cap_pair_credential_held: PairCredentialHeldPort,
    cap_run_retention: RunRetentionPort,
    compiler: WorkflowCompiler,
    msource: MaintenanceSource | None,
    door: Door | None,
    context: CommandContext,
) -> None:
    """Re-drive a one-shot resolve on a recorded FAIL (INT-FC-R75): thread the
    reviewer's findings into a fresh resolve+review that REVISES the open PR, retire
    the superseded ledger row, and track the new run. The engine has no operator to
    enter a credential, so it reuses the ticket's persisted one; with none, it parks
    visibly rather than looping on a drive it cannot launch. ``findings`` is the
    body of the review that decided the FAIL, as the judge read it (a home PR's reviews
    ride on the pair's credential and are not re-readable here); ``home`` rides into the compile
    so a Managed re-drive clones their repository beside our ticket, as the first
    drive did (INT-FC-R131)."""
    context.authorize("maintenance.drive", repo)
    try:
        if home is not None:
            if door is None:
                raise SourceUnavailable("repository home source is unavailable")
            pr = door.pull_request(home.repo, number, home.credential)
        else:
            if msource is None:
                raise SourceUnavailable("maintenance source is unavailable")
            pr = msource.pr(repo, number)
        source_revision = pr.head_sha if pr else ""
        if not pr or pr.state != "open" or pr.merged:
            raise SourceUnavailable(
                "the failed pull request is not authoritatively open"
            )
        if len(source_revision) != 40 or any(
            character not in "0123456789abcdef" for character in source_revision
        ):
            raise SourceUnavailable("the failed pull request head is unavailable")
    except (OperationUnknown, PermissionDenied):
        raise
    except (
        SourceUnavailable,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    ) as exc:
        entry["acted"] = True
        entry["result"] = f"parked: PR #{number} source revision unavailable ({exc})"
        return
    slug = partial(helper_slug)(repo)
    if (
        not partial(helper_has_delivery_cred, credentials=credentials)(slug)
        or credentials is None
    ):
        entry["acted"] = True
        entry["result"] = (
            f"parked: PR #{number} FAILed and no persisted credential to re-drive"
        )
        return
    try:
        refuse_foreign_seat(
            partial(helper_target_selection, config=config)(repo), context
        )
    except SeatRefused as exc:
        entry["acted"] = True
        entry["result"] = f"parked: PR #{number} FAILed; {exc}"
        return
    cfg = partial(helper_with_delivery_config, cap_delivery_config=cap_delivery_config)(
        repo, RunConfig(worker_credential=None, repo_target=repo, repo_rights=True)
    )
    run_id = (
        "m-"
        + sha256(
            f"{old_handle}:{repo}:{ticket}:{number}:{attempts}".encode()
        ).hexdigest()[:12]
    )
    try:
        workflow = compiler.compile_maintenance(
            repo,
            "resolve",
            ticket,
            MaintenanceMode.ONE_SHOT,
            cfg,
            run_id=run_id,
            source_revision=source_revision,
            credential_secret=credentials.delivery_ref(slug),
            feedback=findings,
            worker_image=worker_image,
            deadline_seconds=cfg.worker_timeout_seconds,
            git_identities=partial(
                helper_git_identities_map, config=config, cap_git_roles=cap_git_roles
            )(),
            retention=partial(
                helper_retention_gc, cap_run_retention=cap_run_retention
            )(),
            home=partial(
                helper_pair_home, cap_pair_credential_held=cap_pair_credential_held
            )(home)
            if home is not None
            else None,
            catalog=partial(helper_agent_catalog, studios=studios)(),
        )
        new_handle = workflows.submit(workflow)
    except (OperationUnknown, PermissionDenied):
        raise
    except (SourceUnavailable, ValueError, RuntimeError) as exc:
        entry["acted"] = True
        entry["result"] = (
            f"parked: PR #{number} FAILed and the re-drive did not submit ({exc})"
        )
        return
    partial(helper_track_oneshot, observations=observations)(
        new_handle,
        repo,
        ticket,
        f"attempt {attempts + 1}/{MAX_RESOLVE_ATTEMPTS}: re-driving resolve on the review's findings",
    )
