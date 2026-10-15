from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess

from orchestrator.adapters.outbound.settings.object_name import _rfc1123
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.repository_identity import RepositoryIdentity


class K8sConfigStore:
    def __init__(self, namespace: str = "foundry-console") -> None:
        self._ns = namespace

    @staticmethod
    def _run(*args, **kwargs):
        try:
            return subprocess.run(*args, **kwargs, check=False, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SourceUnavailable("Kubernetes store is unavailable") from exc

    def _cm(self, name: str) -> str:
        return _rfc1123(f"fc-{name}")

    def _sec(self, name: str) -> str:
        return _rfc1123(f"fc-{name}-key")

    def get_setting(self, name: str) -> dict:
        # Symmetric with put_setting: off the cluster there is nothing to read, so don't
        # shell out to kubectl (which blocks on discovery retries when unreachable).
        if os.environ.get("FC_LIVE") != "1":
            return {"configured": False}
        proc = self._run(
            ["kubectl", "get", "configmap", self._cm(name), "-n", self._ns, "--ignore-not-found", "-o", "jsonpath={.data}"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("worker settings could not be read")
        try:
            fields = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except ValueError as exc:
            raise SourceUnavailable("worker settings are malformed") from exc
        if not isinstance(fields, dict) or any(not isinstance(value, str) for value in fields.values()):
            raise SourceUnavailable("worker settings are malformed")
        return {**fields, "configured": self._secret_exists(name)}

    def put_setting(self, name: str, fields: dict, secret: str | None) -> dict:
        if os.environ.get("FC_LIVE") != "1":
            return {**fields, "configured": bool(secret)}
        self._apply({
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": self._cm(name), "namespace": self._ns},
            "data": {k: str(v) for k, v in fields.items()},
        })
        if secret:
            self._apply({
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": self._sec(name), "namespace": self._ns},
                "stringData": {"value": secret},
            })
        return self.get_setting(name)

    def _apply(self, manifest: dict) -> None:
        # --validate=false: the image's kubectl is the latest release, and its client-side schema check
        # panics on this cluster's OpenAPI document, so every write fails. The manifests are built here
        # from fixed templates, and the API server still validates them on apply.
        proc = self._run(
            ["kubectl", "apply", "--validate=false", "-f", "-"],
            input=json.dumps(manifest), text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("Kubernetes setting write was not confirmed")

    def _secret_exists(self, name: str) -> bool:
        proc = self._run(
            ["kubectl", "get", "secret", self._sec(name), "-n", self._ns, "--ignore-not-found", "-o", "name"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("worker identity credential could not be read")
        return bool(proc.stdout.strip())

    def get_secret(self, name: str) -> str:
        """Read a setting's secret value live (server-side only; never exposed by a door)."""
        if os.environ.get("FC_LIVE") != "1":
            return ""
        proc = self._run(
            ["kubectl", "get", "secret", self._sec(name), "-n", self._ns, "--ignore-not-found", "-o", "jsonpath={.data.value}"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise SourceUnavailable("setting credential could not be read")
        if not proc.stdout.strip():
            return ""
        try:
            return base64.b64decode(proc.stdout.strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise SourceUnavailable("setting credential is malformed") from exc

    def list_settings(self, prefix: str) -> list[dict]:
        """Every setting whose name starts with prefix (e.g. 'agent-'): its public fields
        plus a display name and whether its secret is set. Never the secret value."""
        if os.environ.get("FC_LIVE") != "1":
            return []
        cms = self._run(
            ["kubectl", "get", "configmap", "-n", self._ns, "-o", "json"], text=True, capture_output=True
        )
        if cms.returncode != 0:
            raise SourceUnavailable("settings inventory could not be read")
        try:
            inventory = json.loads(cms.stdout)
        except json.JSONDecodeError as exc:
            raise SourceUnavailable("settings inventory is malformed") from exc
        if not isinstance(inventory, dict) or not isinstance(inventory.get("items"), list):
            raise SourceUnavailable("settings inventory is malformed")
        secs = self._run(
            ["kubectl", "get", "secret", "-n", self._ns, "-o", "name"], text=True, capture_output=True
        )
        if secs.returncode != 0:
            raise SourceUnavailable("settings credential inventory could not be read")
        secret_names = set(secs.stdout.split())
        out = []
        for item in inventory["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
                raise SourceUnavailable("settings inventory is malformed")
            cm_name = item.get("metadata", {}).get("name", "")
            if not isinstance(cm_name, str):
                raise SourceUnavailable("settings inventory is malformed")
            if not cm_name.startswith(f"fc-{prefix}"):
                continue
            setting = cm_name[len("fc-"):]  # e.g. agent-myclaude
            data = item.get("data", {}) or {}
            if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
                raise SourceUnavailable("settings inventory is malformed")
            out.append({
                **data,
                "name": data.get("name") or setting[len(prefix):],
                "configured": f"secret/fc-{setting}-key" in secret_names,
            })
        return out

    def delete_setting(self, name: str) -> None:
        """Delete a setting's ConfigMap + Secret. Raises on failure (e.g. RBAC forbids
        the delete verb) - a swallowed exit code here once made the API answer
        'deleted' while the agent quietly survived."""
        if os.environ.get("FC_LIVE") != "1":
            return
        for kind, obj in (("configmap", self._cm(name)), ("secret", self._sec(name))):
            proc = self._run(
                ["kubectl", "delete", kind, obj, "-n", self._ns, "--ignore-not-found"],
                text=True,
                capture_output=True,
            )
            if proc.returncode != 0:
                raise SourceUnavailable("Kubernetes setting deletion was not confirmed")

    def repository_identity(self, slug: str) -> RepositoryIdentity | None:
        if os.environ.get("FC_LIVE") != "1":
            raise SourceUnavailable("repository settings binding is unavailable outside the live store")
        proc = self._run(["kubectl", "get", "configmap", self._cm("repository-identity-" + slug), "-n", self._ns, "--ignore-not-found", "-o", "json"], text=True, capture_output=True)
        if proc.returncode != 0:
            raise SourceUnavailable("repository settings binding could not be read")
        if not proc.stdout.strip():
            return None
        try:
            fields = json.loads(proc.stdout)["data"]
            return RepositoryIdentity(str(fields["repository"]), str(fields["repository_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("repository settings binding is invalid") from exc

    def bind_repository_identity(self, slug: str, identity: RepositoryIdentity) -> None:
        if os.environ.get("FC_LIVE") != "1":
            raise SourceUnavailable("repository settings binding is unavailable outside the live store")
        self._apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": self._cm("repository-identity-" + slug), "namespace": self._ns}, "data": {"repository": identity.repository, "repository_id": identity.stable_id}})
