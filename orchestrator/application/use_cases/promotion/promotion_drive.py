"""PromotionDrive over consumed application contracts."""
from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.execution.workflow_compiler import (
    WorkflowCompiler,
)
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.ports.outbound.repositories.repository_incarnations import (
    RepositoryIncarnations,
)
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.promotion import pair_door_shut, parse_contract
from orchestrator.application.release_train import latest_version
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.runs.prepare_config import (
    prepare_agents,
    prepare_config,
)
from orchestrator.application.services.runs.retention_gc import helper_retention_gc
from orchestrator.application.services.settings.pair_refs import helper_pair_refs
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.prepared_promotion_command import (
    PreparedPromotionCommand,
)
from orchestrator.domain.model.promotion_drive_result import PromotionDriveResult
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.services.promotion_launch import (
    PROMOTE_AGENT,
    PromotionRefused,
    refuse_promotion,
)


class PromotionDrive:

    def __init__(self, *, config: ConfigStore | None, credentials: CredentialStore | None, msource: MaintenanceSource | None, psource: PromotionSource | None, studios: StudioGateway | None, worker_image: str, workflows: WorkflowRunner | None, cap_git_roles: GitRolesPort, cap_pair_credential_held: PairCredentialHeldPort, cap_run_retention: RunRetentionPort, admission: OperationAdmission, compiler: WorkflowCompiler, incarnations: RepositoryIncarnations) -> None:
        self.config = config
        self.credentials = credentials
        self.msource = msource
        self.psource = psource
        self.studios = studios
        self.worker_image = worker_image
        self.workflows = workflows
        self.cap_git_roles = cap_git_roles
        self.cap_pair_credential_held = cap_pair_credential_held
        self.cap_run_retention = cap_run_retention
        self.admission = admission
        self.compiler = compiler
        self.incarnations = incarnations

    def _prepare(self, repo: str, target_name: str, release: str='', *, context: CommandContext, operation_id: str, expected_revision: str | None=None) -> PreparedPromotionCommand:
        """Perform one declared target's door, as a compiled worker run (issue #131).

        The registry declares a door (the target, the name of its credential); this act is
        what performs it: the console holds the credential and carries it to a worker that
        can push. Without this act a `kind: repository` target is a name with nothing
        behind it.

        Every refusal happens HERE, before a pod exists, because each one is something the
        operator can act on: an app that is Managed (promotion never reaches it), a target that
        was never declared, a door whose credential the platform does not hold, and a release
        that does not exist. The proven check itself stays in the skill's pre-flight, where it
        can read the live registry and the entry environment; this refuses what is knowable
        without leaving the console.
        """
        if self.psource is None or self.msource is None or self.workflows is None:
            raise PromotionRefused('this console has no repo-host credential configured')
        revision = self.psource.repository_revision(repo)
        if expected_revision is not None and revision != expected_revision:
            raise Conflict("promotion source revision changed")
        declared, problem = parse_contract(self.psource.contract_text(repo, revision=revision))
        if problem:
            raise PromotionRefused(f"the app's contract is malformed ({problem}); fix it in the repo before promoting anything")
        target = next((t for t in declared if t.name == target_name), None)
        tags = self.msource.tags(repo)
        release = (release or '').strip() or latest_version(tags)
        if release.lstrip("v") not in {tag.lstrip("v") for tag in tags}:
            raise PromotionRefused("the selected release does not exist")
        installs = self.psource.deploy_installs(repo)
        refuse_promotion(target=target, target_name=target_name, declared=declared, release=release, door_shut=pair_door_shut(target, self.cap_pair_credential_held.execute) if target is not None and self.config is not None else '', has_entry_environment=bool(installs))
        assert target is not None
        cfg, identity = prepare_config(repo, RunConfig('', repo, True), config=self.config, credentials=self.credentials, incarnations=self.incarnations, context=context)
        run_id = 'p-' + self.admission.key(context, 'promotion.drive', repo, operation_id)[:12]
        secret = self.credentials.delivery_ref(helper_slug(repo))
        identities, catalog = prepare_agents({PROMOTE_AGENT}, studios=self.studios, config=self.config, roles=self.cap_git_roles.execute())
        workflow = self.compiler.compile_promotion(repo, target, release, cfg, run_id=run_id, source_revision=revision, credential_secret=secret, pair=partial(helper_pair_refs, cap_pair_credential_held=self.cap_pair_credential_held)(target.credential) if target.kind is TargetKind.REPOSITORY else None, git_identity=identities[PROMOTE_AGENT], catalog=catalog, worker_image=self.worker_image, deadline_seconds=cfg.worker_timeout_seconds, retention=partial(helper_retention_gc, cap_run_retention=self.cap_run_retention)())
        context.authorize("promotion.drive", repo)
        return PreparedPromotionCommand(workflow, run_id, target, release, revision, identity.stable_id)

    def _dispatch(self, prepared: PreparedPromotionCommand) -> PromotionDriveResult:
        handle = self.workflows.submit(prepared.workflow)
        if not handle:
            raise SourceUnavailable("workflow launch outcome is unavailable")
        target = prepared.target
        return PromotionDriveResult(prepared.run_id, handle, target.name, prepared.release, target.kind)

    def execute(self, repo: str, target_name: str, release: str='', *, context: CommandContext, operation_id: str, expected_revision: str | None=None) -> PromotionDriveResult:
        context.authorize('promotion.drive', repo)
        result = []
        prepared = []
        evidence = {}

        def validate():
            prepared.append(self._prepare(repo=repo, target_name=target_name, release=release, context=context, operation_id=operation_id, expected_revision=expected_revision))
            evidence.update(source_revision=prepared[0].source_revision, repository_id=prepared[0].repository_id, run_id=prepared[0].run_id)

        def dispatch():
            context.authorize("promotion.drive", repo)
            value = self._dispatch(prepared[0])
            result.append(value)
            return safe_value(value)
        retained = self.admission.execute(context, 'promotion.drive', repo, operation_id, safe_value({'repo': repo, 'target_name': target_name, 'release': release, 'expected_revision': expected_revision}), dispatch, secret_write=False, validate=validate, evidence=evidence)
        if result:
            return result[0]
        return restore_result(retained, get_type_hints(self._dispatch).get('return', object))
