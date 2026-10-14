"""Build the worker's immutable playbook payload from the helper manifest's commit."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


def bundle(manifest_path: Path, clone: str = "") -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision = manifest["ref"]
    command = (
        [
            "git",
            "-C",
            clone,
            "archive",
            revision,
            "AI-PLAYBOOK.md",
            "galaxies",
            "scripts",
        ]
        if clone
        else ["gh", "api", f"repos/{manifest['repo']}/tarball/{revision}"]
    )
    archive = subprocess.run(
        command, check=True, capture_output=True, timeout=120
    ).stdout
    files: dict[str, bytes] = {"REVISION": (revision + "\n").encode()}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
        for member in source:
            path = PurePosixPath(member.name)
            if not clone:
                path = PurePosixPath(*path.parts[1:])
            if not path.parts or path.parts[0] not in {
                "AI-PLAYBOOK.md",
                "galaxies",
                "scripts",
            }:
                continue
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe playbook archive member")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Playbook payload must contain ordinary files")
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable playbook archive member")
            files[str(path)] = stream.read()
    if "AI-PLAYBOOK.md" not in files:
        raise ValueError("The pinned playbook has no entry point")
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as compressed, tarfile.open(fileobj=compressed, mode="w") as target:
        for name, content in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o644
            target.addfile(info, io.BytesIO(content))
    payload = output.getvalue()
    bundle_path = manifest_path.with_name("playbook.tar.gz")
    bundle_path.write_bytes(payload)
    manifest["runtime_bundle"] = {
        "file": "playbook.tar.gz",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "files": len(files),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--clone", default="")
    args = parser.parse_args()
    bundle(args.manifest, args.clone)
