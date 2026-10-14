"""Bind retained target settings to authoritative repository incarnations."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.domain.delivery import delivery_slug
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.repository_identity import RepositoryIdentity


class RepositoryIncarnation:
    def __init__(
        self,
        repositories: RepoStore,
        settings: ConfigStore,
        credentials: CredentialStore,
    ) -> None:
        self._repositories = repositories
        self._settings = settings
        self._credentials = credentials

    def observe(self, repository: str) -> RepositoryIdentity | None:
        """None means the repository address is authoritatively absent."""
        return self._repositories.repository_identity(repository)

    def verify_current(self, repository: str) -> RepositoryIdentity:
        """Refuse target credentials unless their retained binding matches the live host ID."""
        current = self.observe(repository)
        if current is None:
            raise SourceUnavailable("repository identity is unavailable")
        bound = self._settings.repository_identity(delivery_slug(current.repository))
        if bound is None or bound.stable_id != current.stable_id:
            raise SourceUnavailable(
                "target settings require repository identity reconciliation"
            )
        return current

    def adopt(self, repository: str) -> RepositoryIdentity:
        """Bind target settings the operator writes to the repository as it exists now.
        Settings retained under its name that are bound to another incarnation, or bound to
        none, are cleared before the write: every repository holding settings is bound when
        the binding is introduced, so unbound settings outlived their repository."""
        current = self.observe(repository)
        if current is None:
            raise SourceUnavailable("repository identity is unavailable")
        slug = delivery_slug(current.repository)
        bound = self._settings.repository_identity(slug)
        if bound is not None and bound.stable_id == current.stable_id:
            return current
        self._credentials.delete_delivery(slug)
        self._settings.delete_setting("target-" + slug)
        self._settings.bind_repository_identity(slug, current)
        return current

    def reconcile(
        self, repository: str, before: RepositoryIdentity | None
    ) -> RepositoryIdentity:
        current = self.observe(repository)
        if current is None:
            raise SourceUnavailable(
                "the established repository identity is unavailable"
            )
        slug = delivery_slug(current.repository)
        bound = self._settings.repository_identity(slug)
        replaced = bound is not None and bound.stable_id != current.stable_id
        created = before is None
        changed_during_establish = (
            before is not None and before.stable_id != current.stable_id
        )
        if replaced or created or changed_during_establish:
            self._credentials.delete_delivery(slug)
            self._settings.delete_setting("target-" + slug)
        if bound != current:
            self._settings.bind_repository_identity(slug, current)
        return current
