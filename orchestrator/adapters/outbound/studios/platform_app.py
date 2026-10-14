"""Normalize platform wire declarations into application facts."""

import re
from urllib.parse import urlsplit

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.platform_app import PlatformApp


def platform_app(row: object) -> PlatformApp:
    if not isinstance(row, dict):
        raise SourceUnavailable("platform application observation is malformed")
    name = row.get("name")
    manifest = row.get("manifest")
    if not isinstance(name, str) or not name or (manifest is not None and not isinstance(manifest, dict)):
        raise SourceUnavailable("platform application observation is malformed")
    manifest = manifest or {}
    repository = row.get("repo")
    declared_url = manifest.get("repo_url")
    url_repository = ""
    if declared_url:
        if not isinstance(declared_url, str):
            raise SourceUnavailable("platform repository declaration is malformed")
        url = urlsplit(declared_url)
        parts = url.path.strip("/").removesuffix(".git").split("/")
        if not url.hostname or len(parts) != 2:
            raise SourceUnavailable("platform repository declaration is malformed")
        url_repository = "/".join(parts)
    if repository in (None, ""):
        repository = url_repository or name
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?", repository):
        raise SourceUnavailable("platform repository declaration is malformed")
    if url_repository:
        # The platform reports an undeclared repository as the app's name; the deployed
        # source URL then names the repository.
        defaulted = repository.lower() == name.lower()
        if not defaulted and repository.lower() not in (url_repository.lower(), url_repository.rsplit("/", 1)[-1].lower()):
            raise SourceUnavailable("platform repository declarations disagree")
        repository = url_repository
    values = {"status": row.get("status"), "hostname": manifest.get("hostname") or "", "revision": row.get("revision") or manifest.get("revision") or "", "role": row.get("role")}
    if any(value is not None and not isinstance(value, str) for value in values.values()):
        raise SourceUnavailable("platform application observation is malformed")
    return PlatformApp(name, repository, row.get("manifest") is not None, **values)
