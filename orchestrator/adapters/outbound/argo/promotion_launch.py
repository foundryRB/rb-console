"""Render the execution contract as an Argo Workflow."""
from __future__ import annotations

from orchestrator.adapters.outbound.argo.retention import gc_policy
from orchestrator.adapters.outbound.argo.worker_template import (
    _slug,
    _worker_template,
    bind_agent,
)
from orchestrator.domain.delivery import PLAYBOOK_STUDIO
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.git_identity import GitIdentity
from orchestrator.domain.model.pair_credential import PairCredential
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.services.promotion_launch import (
    PROMOTE_AGENT,
    PROMOTE_PHASE,
    PROMOTE_SKILL,
    PromotionRefused,
    build_promotion_prompt,
)

_API = "argoproj.io/v1alpha1"

def compile_promotion_workflow(
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
    public_domain: str = "",
    namespace: str = "foundry-console",
    service_account: str = "foundry-console-worker",
    gc: dict | None = None,
    max_attempts: int = 3,
    deadline_seconds: int = 1800,
) -> dict:
    """One promotion as a submittable Argo Workflow: a single worker running the promote skill.

    One step, never two. A promotion's verification is the skill's own (terms verify deployed,
    acceptance verifies proven) and its acceptance may be a signal that answers minutes or days
    later, on a network this cluster has no path into - so there is no second step to compile,
    and nothing here waits on a pair's review. The run ends when the door is performed; where
    the target then stands is derived on read, as it always was.

    A repository target with no ``pair`` is a mis-compile, not a degraded run: its door is a
    push to a repository we do not own, and a worker that reaches it without the pair's own
    grant would either fail at auth or - far worse - succeed on some other credential.
    """
    if target.kind is TargetKind.REPOSITORY and pair is None:
        raise PromotionRefused(
            f"target {target.name!r} is another organization's repository and no pair "
            f"credential was resolved for {target.credential or '(unnamed)'}"
        )

    template = _worker_template(
        "worker-promote",
        PROMOTE_PHASE,
        PROMOTE_SKILL,
        repo,
        "",  # no .delivery/ record: a promotion writes none
        "",  # no gate: a promotion closes on its declared acceptance, not on a signature
        (PLAYBOOK_STUDIO,),
        build_promotion_prompt(repo, target, release),
        run_id,
        credential_secret or f"fc-run-{run_id}",
        RunMode.INTERACTIVE,  # no stamp block; a promotion signs nothing
        config.worker_provider,
        config.worker_base_url,
        config.worker_model,
        worker_image,
        max_attempts,
        deadline_seconds,
        # The door's own facts, so the entrypoint verifies the artifact rather than the exit
        # code: which target, and the release it must carry.
        promote_target=target.name, public_domain=public_domain,
        release=release,
        # Who the commit is authored by. Assigned through the same Settings role map every
        # other phase uses; unassigned means no git credentials at all, and the push fails
        # loudly rather than some default identity promoting on nobody's authority.
        git=git_identity,
        agent=bind_agent(PROMOTE_AGENT, catalog),
        # What authorizes the push to THEIR repository, when the door is a pair's, and the
        # repository path the entrypoint scopes that authorization to.
        pair=pair,
        pair_repo=target.repo if target.kind is TargetKind.REPOSITORY else "",
    )
    template["container"].setdefault("env", []).append({"name": "FC_SOURCE_REVISION", "value": source_revision})
    return {
        "apiVersion": _API,
        "kind": "Workflow",
        "metadata": {
            "generateName": f"promote-{_slug(target.name)}-{_slug(repo)}-",
            "namespace": namespace,
            "annotations": {"foundry-console/repository": repo},
            "labels": {
                "foundry-console/run": run_id,
                "foundry-console/promotion": _slug(target.name),
                "foundry-console/repo-slug": _slug(repo),
            },
        },
        "spec": {
            "entrypoint": "line",
            "serviceAccountName": service_account,
            **(gc or gc_policy()),
            "templates": [
                {"name": "line", "steps": [[{"name": "promote", "template": "worker-promote"}]]},
                template,
            ],
        },
    }
