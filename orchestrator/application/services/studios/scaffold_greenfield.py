"""Studios shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.definitions import logger
from orchestrator.application.services.studios.repo_is_there import helper_repo_is_there
from orchestrator.domain.exceptions.studio_tool_error import StudioToolError


def helper_scaffold_greenfield(
    target: str,
    request: str,
    app_name: str = "",
    *,
    repos: RepoStore,
    studios: StudioGateway | None,
) -> str:
    """Templated birth via platform-studio; returns how the repo was born
    ("templated", "bare", or "adopted") for the establish log.

    Not every refusal is the same, and treating them alike is what let a
    delivery start on a repo carrying no contract. Three outcomes:

    * The studio is absent or unreachable -> the platform is opt-in and a
      delivery must still be establishable without it, so fall back to the
      bare create-or-adopt. Logged, because "born bare" is a fact about the
      repo the operator will need at build time, not a non-event.
    * The repository already exists -> adopting it, which is ordinary.
    * The name is not a lowercase DNS label AND the repo is already there ->
      the studio can never template it, but the operator did not choose that
      name: establish also routes repos that already exist on the org
      (``SolveOS``) through this call, and the console offers no way to
      rename one. Fall back to the bare create-or-adopt, logged, rather than
      blocking the delivery (#67). The same refusal over a repo that does
      NOT exist is the greenfield case, where the caller DID choose the name
      and a 422 they can act on beats a repo silently born bare under a
      typo, so it falls through to the raise below.
    * Anything else -> RAISE. The studio refused for a reason it can state,
      and the one thing establish must never do is carry on as if a repo
      that failed to scaffold were a healthy one; the caller surfaces it as
      a 422 rather than deferring the discovery to build-and-ship.
    """
    if studios is None:
        return "bare"
    repo = target.split("/")[-1].strip()
    if not repo:
        return "bare"
    name = app_name.strip() or repo
    display = name.replace("-", " ").title()
    first_line = request.strip().splitlines()[0].strip() if request.strip() else ""
    description = (first_line or f"{display} (Foundry delivery)")[:200]
    try:
        studios.create_app_repo(name, display, description, repo)
    except StudioToolError as exc:
        if exc.error == "AlreadyExistsError":
            return "adopted"
        if exc.error == "SyncFailedError":
            logger.warning("platform-studio cannot create repos; %s born bare", name)
            return "bare"
        if exc.error == "InvalidAppNameError" and partial(
            helper_repo_is_there, repos=repos
        )(target):
            logger.warning(
                "platform-studio cannot template %s (%s); born bare", name, exc.detail
            )
            return "bare"
        raise RuntimeError(
            f"platform-studio could not scaffold {name}: {exc.detail}"
        ) from exc
    return "templated"
