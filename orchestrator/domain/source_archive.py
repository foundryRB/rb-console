"""A source archive: an existing application, uploaded as a zip, that a delivery line
grows from. Establish seeds a repository born in that establish with its contents, so
the Scope phase reads the app itself as its input - the recast ground of REF-Delivery
(what the line starts from is read off the repo, never declared).

The archive is screened before a byte of it lands in the org:

* vendored and built trees are skipped (``.git``, ``node_modules``, ``dist``, ``build``,
  the caches): they are reproducible from the source and would bloat a seed commit
  the build replaces anyway;
* env files other than examples are refused, and so is any file carrying a
  secret-shaped string, each named - an app exported from a prototyping tool
  routinely carries its keys in tree, and a commit onto a foundry repo is history
  for good;
* a path that escapes the tree, an empty archive, and an archive over the size cap
  are refused, so the seed is bounded and stays where it was pointed.

Pure: bytes in, files out, refusals raised. No I/O beyond the archive itself.
"""
from __future__ import annotations

import io
import re
import zipfile
from posixpath import normpath

from orchestrator.domain.exceptions.source_archive_error import SourceArchiveError
from orchestrator.domain.model.source_file import SourceFile

MAX_FILES = 4000
MAX_UNPACKED_BYTES = 40 * 1024 * 1024
_SCAN_BYTES = 1024 * 1024  # a secret lives near the top of a file, not a megabyte in

SKIPPED_DIRS = frozenset({
    ".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", ".output",
    ".svelte-kit", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".turbo", ".cache", ".parcel-cache", "coverage", ".idea", ".vscode",
    "target", ".gradle", "bin", "obj",
})
SKIPPED_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
_ENV_EXAMPLES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})

_SECRET_SHAPES: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("an AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("an OpenAI-style secret key", re.compile(rb"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}")),
    ("a GitHub token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("a Slack token", re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a Stripe live key", re.compile(rb"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
    ("a private key block", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
)






def _clean_path(raw: str) -> str | None:
    """The entry's path as a safe repo-relative POSIX path, or None for an entry that
    escapes the tree (absolute, drive-lettered, or climbing with ``..``)."""
    path = raw.replace("\\", "/").strip("/")
    if not path or ":" in path.split("/", 1)[0]:
        return None
    clean = normpath(path)
    if clean.startswith(("../", "/")) or clean == "..":
        return None
    return clean


def _is_env_file(name: str) -> bool:
    return (name == ".env" or name.startswith(".env.")) and name not in _ENV_EXAMPLES


def _secret_shape(data: bytes) -> str | None:
    head = data[:_SCAN_BYTES]
    if b"\x00" in head:
        return None  # binary: an image is not a key file
    for label, pattern in _SECRET_SHAPES:
        if pattern.search(head):
            return label
    return None


def unpack_source_archive(payload: bytes) -> list[SourceFile]:
    """The archive's files, screened and sorted by path, ready to seed a repository.

    A single wrapping folder (``my-app-main/`` around everything, the way hosts and
    export tools zip a project) is stripped, so the app lands at the repo root. Raises
    ``SourceArchiveError`` naming every refused file, so one upload reports the whole
    list rather than one at a time."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise SourceArchiveError("the upload is not a zip archive") from exc

    escaped: list[str] = []
    members: list[tuple[str, zipfile.ZipInfo]] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        clean = _clean_path(info.filename)
        if clean is None:
            escaped.append(info.filename)
            continue
        members.append((clean, info))
    if escaped:
        raise SourceArchiveError(
            "the archive carries paths that escape the tree: " + ", ".join(sorted(escaped))
        )

    members = _strip_wrapping_folder(members)

    kept: list[tuple[str, zipfile.ZipInfo]] = []
    env_files: list[str] = []
    for path, info in members:
        parts = path.split("/")
        if any(part in SKIPPED_DIRS for part in parts[:-1]) or parts[-1] in SKIPPED_FILES:
            continue
        if _is_env_file(parts[-1]):
            env_files.append(path)
            continue
        kept.append((path, info))
    if env_files:
        raise SourceArchiveError(
            "the archive carries env files, which would commit their secrets for good: "
            + ", ".join(sorted(env_files))
            + " - remove them (keep a .env.example) and upload again"
        )
    if not kept:
        raise SourceArchiveError("the archive holds no source files once vendored and built trees are skipped")
    if len(kept) > MAX_FILES:
        raise SourceArchiveError(f"the archive holds {len(kept)} files; the seed cap is {MAX_FILES}")
    unpacked = sum(info.file_size for _, info in kept)
    if unpacked > MAX_UNPACKED_BYTES:
        raise SourceArchiveError(
            f"the archive unpacks to {unpacked // (1024 * 1024)} MB; the seed cap is "
            f"{MAX_UNPACKED_BYTES // (1024 * 1024)} MB"
        )

    files: list[SourceFile] = []
    leaking: list[str] = []
    for path, info in kept:
        data = archive.read(info)
        shape = _secret_shape(data)
        if shape:
            leaking.append(f"{path} (looks like {shape})")
            continue
        files.append(SourceFile(path, data))
    if leaking:
        raise SourceArchiveError(
            "the archive carries secret-shaped strings, which would commit them for good: "
            + ", ".join(sorted(leaking))
            + " - move them out of the tree and upload again"
        )
    return sorted(files, key=lambda f: f.path)


def _strip_wrapping_folder(
    members: list[tuple[str, zipfile.ZipInfo]],
) -> list[tuple[str, zipfile.ZipInfo]]:
    """Drop the one folder every entry sits under, when there is exactly one and nothing
    sits beside it: ``app-main/src/x`` becomes ``src/x``. An archive whose root holds
    files, or more than one folder, is already at its root."""
    heads = {path.split("/", 1)[0] for path, _ in members}
    if len(heads) != 1 or any("/" not in path for path, _ in members):
        return members
    return [(path.split("/", 1)[1], info) for path, info in members]
