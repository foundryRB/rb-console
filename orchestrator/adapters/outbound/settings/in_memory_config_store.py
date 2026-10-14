from __future__ import annotations

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.repository_identity import RepositoryIdentity


class InMemoryConfigStore:
    def __init__(self) -> None:
        self._fields: dict[str, dict] = {}
        self._secrets: dict[str, str] = {}

    def get_setting(self, name: str) -> dict:
        return {**self._fields.get(name, {}), "configured": bool(self._secrets.get(name))}

    def put_setting(self, name: str, fields: dict, secret: str | None) -> dict:
        self._fields[name] = dict(fields)
        if secret:  # an empty secret leaves the stored one unchanged
            self._secrets[name] = secret
        return self.get_setting(name)

    def get_secret(self, name: str) -> str:
        return self._secrets.get(name, "")

    def list_settings(self, prefix: str) -> list[dict]:
        names = sorted(set(self._fields) | set(self._secrets))
        return [
            {**self._fields.get(n, {}), "name": self._fields.get(n, {}).get("name") or n[len(prefix):], "configured": bool(self._secrets.get(n))}
            for n in names
            if n.startswith(prefix)
        ]

    def delete_setting(self, name: str) -> None:
        self._fields.pop(name, None)
        self._secrets.pop(name, None)

    def repository_identity(self, slug: str) -> RepositoryIdentity | None:
        fields = self._fields.get("repository-identity-" + slug)
        if fields is None:
            return None
        try:
            return RepositoryIdentity(str(fields["repository"]), str(fields["repository_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("repository settings binding is invalid") from exc

    def bind_repository_identity(self, slug: str, identity: RepositoryIdentity) -> None:
        self.put_setting("repository-identity-" + slug, {"repository": identity.repository, "repository_id": identity.stable_id}, None)
