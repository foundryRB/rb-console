"""Declare a target against a freshly observed contract revision."""
from orchestrator.application.ports.inbound.promotion.promotion_state import (
    PromotionStatePort,
)
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.promotion import parse_contract
from orchestrator.application.promotion_declare import (
    ContractError,
    declare_target,
    render_contract,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.promotion.entry_environments import (
    helper_entry_environments,
)
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext


class DeclarePromotionTarget:
    def __init__(self, *, psource: PromotionSource | None,
                 cap_promotion_state: PromotionStatePort, observations: ObservationStore,
                 admission: OperationAdmission) -> None:
        self.psource = psource
        self.cap_promotion_state = cap_promotion_state
        self.observations = observations
        self.admission = admission

    def execute(self, repo: str, declaration: dict, author: str = "", *,
                context: CommandContext, operation_id: str,
                expected_revision: str | None = None) -> dict:
        context.authorize("promotion.declare", repo)
        prepared: dict = {}
        evidence: dict = {}

        def validate() -> None:
            if self.psource is None:
                raise SourceUnavailable("A repository source is required to declare a target.")
            revision = self.psource.repository_revision(repo)
            if not revision:
                raise SourceUnavailable("The repository revision could not be observed.")
            if expected_revision and expected_revision != revision:
                raise Conflict("The contract revision changed; refresh before declaring a target.")
            existing, problem = parse_contract(self.psource.contract_text(repo, revision=revision))
            if problem:
                raise ContractError(f"The app's contract is malformed ({problem}); repair it before adding a target")
            installs = self.psource.deploy_installs(repo)
            targets = declare_target(
                existing=existing, name=str(declaration.get("name") or ""),
                kind=str(declaration.get("kind") or ""), install=str(declaration.get("install") or ""),
                environment=str(declaration.get("environment") or ""), repo=str(declaration.get("pair_repo") or ""),
                branch=str(declaration.get("branch") or ""), credential=str(declaration.get("credential") or ""),
                probe_url=str(declaration.get("probe_url") or ""), entry_environments=helper_entry_environments(repo, installs),
            )
            prepared.update(revision=revision, name=targets[-1].name, text=render_contract(targets))
            evidence.update(repository=repo, resource_version=revision)

        def dispatch() -> dict:
            name = prepared["name"]
            sha = self.psource.write_contract(repo, prepared["text"], f"feat(promotion): declare the {name} target",
                                             author=author, expected_revision=prepared["revision"])
            state = self.cap_promotion_state.execute(repo)
            self.observations.metadata.setdefault(repo, {})["promotion_state"] = state
            return {"target": name, "commit": sha, **state}

        return self.admission.execute(
            context, "promotion.declare", repo, operation_id,
            {"declaration": declaration, "author": author, "expected_revision": expected_revision},
            dispatch, validate=validate, evidence=evidence,
        )
