"""CredentialStore over Kubernetes Secrets. A run's worker credential is written to
a per-run Secret (``fc-run-<id>``); a delivery's persisted credential to a per-delivery
Secret keyed by slug (``fc-delivery-<slug>``), so a delivery remembers its model without
re-entry. Only the ref (the Secret name) travels downstream, never the value, and never
into git. Writing is guarded behind FC_LIVE like the other outbound adapters; without
opt-in it returns the ref and writes nothing. The value is passed on stdin, never on the
command line.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def _slugify(slug: str) -> str:
    """An RFC1123 fragment for a Secret name: lowercase, [a-z0-9-]."""
    return re.sub(r"[^a-z0-9-]", "-", (slug or "").lower()).strip("-") or "delivery"


class K8sCredentialStore:
    def __init__(self, namespace: str = "foundry-console") -> None:
        self._ns = namespace

    @staticmethod
    def _run(*args, **kwargs):
        try:
            return subprocess.run(*args, **kwargs, check=False, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SourceUnavailable("Kubernetes store is unavailable") from exc

    def _name(self, run_id: str) -> str:
        return f"fc-run-{run_id}"

    def _delivery_name(self, slug: str) -> str:
        return f"fc-delivery-{_slugify(slug)}"

    def delivery_ref(self, slug: str) -> str:
        """The Secret name a delivery's persisted credential lives under (by slug)."""
        return self._delivery_name(slug)

    def put_delivery(self, slug: str, credential: str) -> str:
        """Persist a delivery's model credential as a namespace Secret keyed by slug, so
        later drives reuse it without re-entry. Never written to git."""
        name = self._delivery_name(slug)
        if os.environ.get("FC_LIVE") != "1":
            return name
        manifest = json.dumps({
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": self._ns, "labels": {"foundry-console/delivery": _slugify(slug)}},
            "stringData": {"worker_credential": credential},
        })
        # --validate=false: the image's kubectl is the latest release, and its client-side schema check
        # panics on this cluster's OpenAPI document, so every write fails. The manifests are built here
        # from fixed templates, and the API server still validates them on apply.
        proc = self._run(
            ["kubectl", "apply", "--validate=false", "-f", "-"], input=manifest, text=True, capture_output=True
        )
        if proc.returncode != 0:
            raise SourceUnavailable("Kubernetes credential write was not confirmed")
        return name

    def has_delivery(self, slug: str) -> bool:
        if os.environ.get("FC_LIVE") != "1":
            return False
        proc = self._run(
            ["kubectl", "get", "secret", self._delivery_name(slug), "-n", self._ns, "--ignore-not-found", "-o", "name"],
            text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("worker credential availability could not be read")
        return bool(proc.stdout.strip())

    def get_delivery(self, slug: str) -> str:
        """The delivery credential's value (server-side only, e.g. for the co-pilot to run
        the model). Never returned by a door."""
        if os.environ.get("FC_LIVE") != "1":
            return ""
        proc = self._run(
            ["kubectl", "get", "secret", self._delivery_name(slug), "-n", self._ns, "--ignore-not-found", "-o", "jsonpath={.data.worker_credential}"],
            text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("delivery credential could not be read")
        if not proc.stdout.strip():
            return ""
        try:
            return base64.b64decode(proc.stdout.strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise SourceUnavailable("delivery credential is malformed") from exc

    def delete_delivery(self, slug: str) -> None:
        if os.environ.get("FC_LIVE") != "1":
            return
        proc = self._run(
            ["kubectl", "delete", "secret", self._delivery_name(slug), "-n", self._ns, "--ignore-not-found"],
            capture_output=True, text=True,
        )

        if proc.returncode != 0:
            raise SourceUnavailable("Kubernetes credential write was not confirmed")

    def run_ref(self, run_id: str) -> str:
        return self._name(run_id)

    def put(self, run_id: str, credential: str) -> str:
        name = self._name(run_id)
        if os.environ.get("FC_LIVE") != "1":
            return name  # not opted in: the ref only, nothing written
        manifest = json.dumps({
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": self._ns, "labels": {"foundry-console/run": run_id}},
            "stringData": {"worker_credential": credential},
        })
        # --validate=false: the image's kubectl is the latest release, and its client-side schema check
        # panics on this cluster's OpenAPI document, so every write fails. The manifests are built here
        # from fixed templates, and the API server still validates them on apply.
        proc = self._run(
            ["kubectl", "apply", "--validate=false", "-f", "-"], input=manifest, text=True, capture_output=True
        )
        if proc.returncode != 0:
            raise SourceUnavailable("Kubernetes credential write was not confirmed")
        return name

    def delete(self, run_id: str) -> None:
        if os.environ.get("FC_LIVE") != "1":
            return
        proc = self._run(
            ["kubectl", "delete", "secret", self._name(run_id), "-n", self._ns, "--ignore-not-found"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("Kubernetes credential write was not confirmed")
