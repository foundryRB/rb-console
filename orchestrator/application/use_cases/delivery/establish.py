"""Establish over consumed application contracts."""

from __future__ import annotations

import re
from urllib.parse import urlsplit
from dataclasses import replace
from functools import partial
from typing import get_type_hints

from orchestrator.application.events import LINE_STARTED, state_fact
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.ports.outbound.repositories.repository_incarnations import (
    RepositoryIncarnations,
)
from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.definitions import logger
from orchestrator.application.services.delivery.demo_app_name import (
    helper_demo_app_name,
)
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.runs.end_runs import helper_end_runs
from orchestrator.application.services.settings.team_roster_store import TeamRosterStore
from orchestrator.application.services.studios.scaffold_greenfield import (
    helper_scaffold_greenfield,
)
from orchestrator.domain.current_lifecycle import (
    CURRENT_LIFECYCLE,
    CURRENT_PLAYBOOK_REF,
)
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.repository_identity import RepositoryIdentity
from orchestrator.domain.model.source_file import SourceFile
from orchestrator.domain.source_archive import unpack_source_archive


class Establish:
    def __init__(
        self,
        *,
        events: EventPublisher | None,
        repos: RepoStore,
        run_log_store: RunLogStore | None,
        source: DeliverySource | None,
        studios: StudioGateway | None,
        workflows: WorkflowRunner | None,
        cap_run_retention: RunRetentionPort,
        admission: OperationAdmission,
        incarnations: RepositoryIncarnations,
        index: DeliveryIndex | None,
        worker_image: str,
        teams: TeamRosterStore,
    ) -> None:
        self.events = events
        self.repos = repos
        self.run_log_store = run_log_store
        self.source = source
        self.studios = studios
        self.workflows = workflows
        self.cap_run_retention = cap_run_retention
        self.admission = admission
        self.incarnations = incarnations
        self.index = index
        self.worker_image = worker_image
        self.teams = teams

    def _execute(
        self,
        target: str,
        request: str = "",
        source: bytes | None = None,
        source_name: str = "",
        app_name: str = "",
        *,
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
        before: RepositoryIdentity | None,
        existing: DeliveryState,
    ) -> DeliveryState:
        """Apply the admitted establish command using its prepared inputs."""
        files: list[SourceFile] = unpack_source_archive(source) if source else []
        birth = (
            "adopted"
            if before is not None
            else partial(
                helper_scaffold_greenfield, repos=self.repos, studios=self.studios
            )(
                target,
                request,
                app_name or partial(helper_demo_app_name, studios=self.studios)(target),
            )
        )
        workspace = self.repos.ensure(target)
        self.incarnations.reconcile(workspace, before)
        # The line belongs to its team from its first moment: the assignment lands before
        # the scratch that makes the repository a line.
        repository_id = context.repository_id(workspace)
        if team and self.teams.execute().team_of(repository_id) != team:
            self.teams.assign(repository_id, team)
        if files:
            birth = f"{birth}+recast"
        logger.info("Established %s (%s)", workspace, birth)
        if not existing.exists:
            partial(
                helper_end_runs,
                run_log_store=self.run_log_store,
                workflows=self.workflows,
                cap_run_retention=self.cap_run_retention,
            )(context.repository_id(workspace))
        self.repos.register(workspace, request, files, source_name)
        configuration = (
            self.source.read_config(workspace) if self.source is not None else {}
        )
        if not configuration.get("lifecycle"):
            self.repos.write_config(
                workspace,
                configuration,
                lifecycle=replace(
                    CURRENT_LIFECYCLE,
                    source_ref=CURRENT_PLAYBOOK_REF,
                    worker_image=self.worker_image,
                ),
            )
        state_fact(
            self.events,
            event_type=LINE_STARTED,
            subject=workspace,
            data={"repo": workspace, "birth": birth},
        )
        if self.source is None:
            raise SourceUnavailable(
                "The new line requires an authoritative delivery source"
            )
        state = self.source.state_of(workspace)
        if self.index is not None:
            self.index.put(state)
        return state

    def execute(
        self,
        target: str,
        request: str = "",
        source: bytes | None = None,
        source_name: str = "",
        app_name: str = "",
        *,
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        # One spelling for every step: the claim, the must-be-new read and the effects
        # all name the repository the creation lands on.
        target = _written_target(target, context)
        if context.initiator_kind == "machine" and (
            source or source_name or app_name or team
        ):
            # The machine caller establishes a line from its ask alone; it seeds the
            # repository itself, with its own repository credential (INT-FC-R173).
            raise PermissionDenied("A machine establish carries the ask alone.")
        team, claimed = self._team(target, team.strip(), context)
        if claimed:
            # A team member opens a line on a new repository for its team: the command is
            # admitted on that one repository, which _validate requires not to exist yet.
            context = replace(
                context,
                repositories=context.repositories | {context.repository_id(target)},
            )
        context.authorize("delivery.establish", target)
        result = []
        prepared = []

        def dispatch():
            value = self._execute(
                target=target,
                request=request,
                source=source,
                source_name=source_name,
                app_name=app_name,
                team=team,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
                before=prepared[0][0],
                existing=prepared[0][1],
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.establish",
            target,
            operation_id,
            safe_value(
                {
                    "target": target,
                    "request": request,
                    "source": source,
                    "source_name": source_name,
                    "app_name": app_name,
                    "team": team,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=False,
            validate=lambda: prepared.append(
                self._validate(
                    target=target,
                    request=request,
                    source=source,
                    source_name=source_name,
                    app_name=app_name,
                    team=team,
                    claimed=claimed,
                    context=context,
                    operation_id=operation_id,
                    expected_revision=expected_revision,
                )
            ),
        )
        if result:
            return result[0]
        return restore_result(
            retained, get_type_hints(self._execute).get("return", object)
        )

    def _validate(
        self,
        target: str,
        request: str = "",
        source: bytes | None = None,
        source_name: str = "",
        app_name: str = "",
        *,
        team: str = "",
        claimed: bool = False,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> RepositoryIdentity | None:
        """Validate fresh establish preconditions before recording command intent. A team
        member's new repository must be new: an existing one joins a team only by an
        admin's assignment."""
        unpack_source_archive(source) if source else []
        before = self.incarnations.observe(target)
        if claimed and before is not None:
            raise ValueError(
                f"{target} already exists and is not assigned to {team}; an admin assigns "
                "an existing repository to a team before its members open a line on it"
            )
        if self.source is None:
            raise SourceUnavailable(
                "Establish requires an authoritative delivery source"
            )
        existing = self.source.state_of(target)
        name = app_name.strip() or target.rsplit("/", 1)[-1]
        if (
            before is None
            and self.studios is not None
            and not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", name)
        ):
            raise ValueError("A new app name must be a lowercase DNS label")
        if source and existing.exists:
            raise ValueError("A recast requires a repository without an open line")
        return before, existing

    def _team(self, target: str, team: str, context: CommandContext) -> tuple[str, bool]:
        """The team a line belongs to, and whether a team member claims a new repository
        for it. An admin may name any team or none. A team member's line belongs to one of
        its teams: the one it names, the repository's own when it is assigned, or its only
        team; a member of several teams chooses. A repository assigned to another team is
        refused."""
        if context.initiator_kind == "machine" or (context.admin and not team):
            return "", False
        roster = self.teams.execute()
        repository_id = context.repository_id(target)
        assigned = roster.team_of(repository_id)
        if context.admin:
            if team and roster.team(team) is None:
                raise ValueError(f"there is no team named {team}")
            return team, False
        if assigned:
            if team and team != assigned:
                raise ValueError(f"{repository_id} belongs to {assigned}")
            if assigned not in context.teams:
                raise PermissionDenied("The repository belongs to another team.")
            return assigned, False
        if not team:
            if len(context.teams) > 1:
                raise ValueError("choose the team the line belongs to")
            if not context.teams:
                raise ValueError("you belong to no team, so you cannot open a line")
            team = next(iter(context.teams))
        if team not in context.teams:
            raise PermissionDenied("The team is not one of the caller's teams.")
        # A new repository is created under the installation's owner whatever owner the
        # target names, so the claim stands only on a repository the installation's scope
        # names, owner included.
        owner = repository_id.split("/", 1)[0]
        if owner != context.installation_id.lower() or not context.may_claim(repository_id):
            raise PermissionDenied("The repository is outside the installation's scope.")
        return team, True


def _written_target(target: str, context: CommandContext) -> str:
    """A target as the repository store reads it: an `https://github.com/` URL becomes its
    `owner/name`, and a `.git` suffix goes; a bare name or `owner/name` keeps its case."""
    target = target.strip()
    if "://" in target:
        context.repository_id(target)
        target = urlsplit(target).path.strip("/")
    return target.removesuffix(".git")
