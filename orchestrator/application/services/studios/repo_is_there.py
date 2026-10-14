"""Check repository presence authoritatively before creating a scaffold."""

from orchestrator.application.ports.outbound.repo_store import RepoStore


def helper_repo_is_there(target: str, *, repos: RepoStore) -> bool:
    return repos.repo_exists(target)
