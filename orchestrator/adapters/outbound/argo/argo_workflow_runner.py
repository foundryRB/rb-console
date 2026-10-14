"""WorkflowRunner over Argo Workflows. Compiling the Workflow is deterministic and
tested; applying it to the cluster is the live step, guarded behind FC_DRIVE_LIVE (the
drive guard, separate from the stores' FC_LIVE), so a run never fires unasked. Reads back
the Workflow phase and the node graph so the Console's Runs surface shows the live DAG.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from urllib.parse import quote

from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.execution_node import ExecutionNode
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
from orchestrator.domain.services.run_history import pod_matches_node
from orchestrator.domain.services.run_policy import STOP_LABEL, STOP_OPERATOR

# Fully-qualified resource: the bare singular "workflow" does not resolve in every
# cluster (it 404s where the group is ambiguous), so always name the API group.
_WF = "workflows.argoproj.io"


def parked_gate(status: dict) -> str | None:
    """WHICH gate a workflow is parked on: the name of its waiting Suspend node with the
    compiler's ``gate-`` prefix dropped, or None when nothing waits. The run's own answer to
    the question a sign has to ask - is this run waiting for THIS gate? - so releasing a run
    is a comparison of two names and never a second reading of the line's records."""
    for n in (status.get("nodes") or {}).values():
        if n.get("type") == "Suspend" and n.get("phase") in ("Running", "Pending"):
            name = str(n.get("displayName") or n.get("templateName") or "")
            return name[len("gate-"):] if name.startswith("gate-") else (name or None)
    return None


def _parked_on_gate(status: dict) -> bool:
    """True when a workflow is parked on a gate: it has a Suspend node still waiting for a
    signature. Argo keeps the overall phase Running in this state (suspend is a node-level
    concept), so both the run row and the graph promote Running->Suspended off this, or a
    wait for a human reads as work in flight. One predicate, so the two never drift."""
    return parked_gate(status) is not None
def stop_reason(meta: dict) -> str | None:
    """Who stopped this run - "superseded" (the console, on a newer drive) or "operator" -
    read off the console's own label. None for a run nobody stopped."""
    return (meta.get("labels") or {}).get(STOP_LABEL) or None


def derive_phase(meta: dict, status: dict, default: str = "Pending") -> str:
    """The Console's phase for a workflow: Argo's own word, with the two promotions every
    surface shares. ONE derivation, read identically by the run row and the node graph, so
    the band, the cockpit pill and the maintenance pane can never disagree about what a run
    is doing.

    - Running + parked on a gate -> **Suspended**: a wait for a signature is not work in flight.
    - stopped by the console -> **Stopping** while it drains, **Stopped** once terminal. Argo
      has no phase for a deliberate close (a shutdown reports Failed), and the executor's
      message is the same string for both reasons, so the promotion reads the console's own
      STOP_LABEL instead. Stopping is a real state, not a blink: `Stop` lets the running step
      finish its exit handler, and a worker's step runs to its whole deadline - reading
      "Running" there shows two live runs for one delivery, the exact confusion superseding
      exists to remove.

    A run that had already finished keeps its own outcome: the promotion touches only the
    phases a shutdown can produce, so a run that was green (or had genuinely failed) when a
    re-drive superseded it still reports what it actually did.
    """
    phase = status.get("phase") or default
    if phase == "Running" and _parked_on_gate(status):
        phase = "Suspended"
    if stop_reason(meta):
        if phase in ("Failed", "Error"):
            return "Stopped"
        if phase in ("Running", "Pending", "Suspended"):
            return "Stopping"
    return phase


def agents_by_template(item: dict) -> dict[str, str]:
    """Which catalog agent each worker template runs as, read off the Workflow object's own
    spec (the ``foundry-console/agent`` label the compiler stamps on each template). The
    Workflow is the run's record, so who ran a step is read back from it rather than from
    a second store, and it outlives the pod."""
    out: dict[str, str] = {}
    for template in (item.get("spec") or {}).get("templates") or []:
        agent = ((template.get("metadata") or {}).get("labels") or {}).get("foundry-console/agent")
        if template.get("name") and agent:
            out[template["name"]] = agent
    return out


def execution_kind(meta: dict) -> str | None:
    """Classify an execution from its exclusive captured source coordinates."""
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    if not isinstance(labels, dict) or not isinstance(annotations, dict):
        return None
    coordinates = {
        "maintenance": labels.get("foundry-console/maintenance"),
        "promotion": labels.get("foundry-console/promotion"),
        "delivery": annotations.get("foundry-console/scratch-ref"),
    }
    if any(value is not None and not isinstance(value, str) for value in coordinates.values()):
        return None
    kinds = [kind for kind, value in coordinates.items() if value]
    return kinds[0] if len(kinds) == 1 else None


def _integer(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SourceUnavailable("Executor numeric evidence is invalid.")
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise SourceUnavailable("Executor numeric evidence is invalid.") from exc


def _workflow_shape(item: object) -> None:
    if not isinstance(item, dict):
        raise SourceUnavailable("Executor workflow evidence is invalid.")
    for field in ("metadata", "status", "spec"):
        if field in item and not isinstance(item[field], dict):
            raise SourceUnavailable("Executor workflow evidence is invalid.")
    metadata = item.get("metadata") or {}
    for field in ("labels", "annotations"):
        if field in metadata and not isinstance(metadata[field], dict):
            raise SourceUnavailable("Executor ownership evidence is invalid.")
    status = item.get("status") or {}
    _text(status.get("phase"))
    nodes = status.get("nodes", {})
    if not isinstance(nodes, dict) or any(
        not isinstance(node, dict) for node in nodes.values()
    ):
        raise SourceUnavailable("Executor node evidence is invalid.")
    templates = (item.get("spec") or {}).get("templates", [])
    if not isinstance(templates, list) or any(
        not isinstance(template, dict) for template in templates
    ):
        raise SourceUnavailable("Executor template evidence is invalid.")
    for template in templates:
        metadata_template = template.get("metadata") or {}
        if not isinstance(metadata_template, dict) or not isinstance(
            metadata_template.get("labels") or {}, dict
        ):
            raise SourceUnavailable("Executor agent evidence is invalid.")
        _text(template.get("name"))
        _text((metadata_template.get("labels") or {}).get("foundry-console/agent"))
    for node in nodes.values():
        for key in (
            "id",
            "displayName",
            "name",
            "type",
            "phase",
            "templateName",
            "message",
            "startedAt",
            "finishedAt",
        ):
            _text(node.get(key))
        outputs = node.get("outputs", {})
        if not isinstance(outputs, dict):
            raise SourceUnavailable("Executor output evidence is invalid.")
        for field in ("children",):
            values = node.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise SourceUnavailable("Executor node references are invalid.")
        artifacts = outputs.get("artifacts", [])
        if not isinstance(artifacts, list) or any(
            not isinstance(artifact, dict) for artifact in artifacts
        ):
            raise SourceUnavailable("Executor artifact evidence is invalid.")
        for artifact in artifacts:
            _text(artifact.get("name"))


def _text(value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise SourceUnavailable("Executor text evidence is invalid.")
    return value


def parse_runs(data: dict) -> list[RunInventoryEntry]:
    """Map an Argo `workflow` list (kubectl -o json) to the Console's run rows, newest
    first. Pure, so it is unit-tested without a cluster."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise SourceUnavailable("Executor inventory evidence is invalid.")
    runs = []
    for item in data["items"]:
        _workflow_shape(item)
        if (
            not isinstance((item.get("metadata") or {}).get("name"), str)
            or not item["metadata"]["name"]
        ):
            raise SourceUnavailable("Executor workflow name is unavailable.")
        meta = item.get("metadata", {})
        labels = meta.get("labels", {})
        annotations = meta.get("annotations") or {}
        try:
            grant = json.loads(
                annotations.get("foundry-console/delegated-grant", "null")
            )
        except (ValueError, TypeError):
            grant = None
        status = item.get("status", {})
        phase = derive_phase(meta, status)
        runs.append(
            RunInventoryEntry(
                handle=f"live:workflow.argoproj.io/{meta.get('name')}",
                name=_text(meta.get("name")),
                run_id=_text(labels.get("foundry-console/run")),
                repository=_text(annotations.get("foundry-console/repository")),
                resource_version=_text(_text(meta.get("resourceVersion"))),
                grant_id=grant.get("grant_id")
                if isinstance(grant, dict) and isinstance(grant.get("grant_id"), str)
                else None,
                mode=_text(labels.get("foundry-console/mode")),
                kind=execution_kind(meta),
                promotion_target=labels.get("foundry-console/promotion")
                if isinstance(labels.get("foundry-console/promotion"), str)
                else None,
                maintenance_act=labels.get("foundry-console/maintenance")
                if isinstance(labels.get("foundry-console/maintenance"), str)
                else None,
                ticket=_integer(labels.get("foundry-console/ticket")),
                repository_slug=_text(labels.get("foundry-console/repo-slug")),
                phase=phase,
                parked_gate=parked_gate(status),
                stop_reason=_text(stop_reason(meta)),
                created_at=_text(meta.get("creationTimestamp")),
                started_at=_text(status.get("startedAt")),
                finished_at=_text(status.get("finishedAt")),
                progress=_text(status.get("progress")),
                agents=tuple(dict.fromkeys(agents_by_template(item).values())),
            )
        )
    return sorted(runs, key=lambda r: r.created_at or "", reverse=True)


def _refusal(node: dict) -> str | None:
    """A worker step's ``refusal`` output (#181): the last line it gave for stopping, kept on
    the Workflow object after the pod is gone. None for a step that wrote none."""
    for parameter in (node.get("outputs") or {}).get("parameters") or []:
        if isinstance(parameter, dict) and parameter.get("name") == "refusal":
            value = str(parameter.get("value") or "").strip()
            return value or None
    return None


def parse_graph(item: dict) -> ExecutionGraph:
    """Map one Argo `workflow` object (kubectl -o json) to the Console's node graph. Pure."""
    _workflow_shape(item)
    status = item.get("status", {})
    agents = agents_by_template(item)
    nodes = [
        ExecutionNode(
            node_id=_text(n.get("id")) or node_id,
            name=_text(n.get("displayName")) or _text(n.get("name")) or node_id,
            kind={
                "Pod": "worker",
                "Suspend": "gate",
                "Steps": "group",
                "StepGroup": "group",
                "DAG": "group",
                "TaskGroup": "group",
            }.get(n.get("type"), "unknown"),
            agent=agents.get(_text(n.get("templateName")) or ""),
            phase="Suspended"
            if n.get("type") == "Suspend" and n.get("phase") in ("Running", "Pending")
            else n.get("phase"),
            template=_text(n.get("templateName")),
            message=_text(n.get("message")),
            exit_code=_integer((n.get("outputs") or {}).get("exitCode")),
            children=tuple(n.get("children") or []),
            started_at=_text(n.get("startedAt")),
            finished_at=_text(n.get("finishedAt")),
            artifacts=tuple(
                [
                    a.get("name")
                    for a in (n.get("outputs") or {}).get("artifacts", [])
                    if a.get("name")
                ]
            ),
            refusal=_refusal(n),
        )
        for node_id, n in (status.get("nodes") or {}).items()
    ]
    # The graph and run row share the derived execution phase used by cockpit controls.
    meta = item.get("metadata", {})
    return ExecutionGraph(
        name=_text(meta.get("name")),
        phase=derive_phase(meta, status, default="Unknown"),
        stop_reason=_text(stop_reason(meta)),
        progress=_text(status.get("progress")),
        nodes=tuple(nodes),
    )


def resume_patch(item: dict) -> list[dict]:
    """A JSON-patch that resumes every suspended node of a workflow (sets it Succeeded) -
    the kubectl-only equivalent of `argo resume` when no Argo server/CLI is present. Pure."""
    ops = []
    for node_id, n in (item.get("status", {}).get("nodes") or {}).items():
        if n.get("type") == "Suspend" and n.get("phase") in ("Running", "Pending"):
            ops.append({"op": "replace", "path": f"/status/nodes/{node_id}/phase", "value": "Succeeded"})
    return ops


class ArgoWorkflowRunner:
    def __init__(self, namespace: str = "foundry-console") -> None:
        self._ns = namespace

    def _read(self, handle: str) -> dict:
        name = self._name(handle)
        if not name:
            raise SourceUnavailable("A live workflow is required.")
        try:
            proc = subprocess.run(
                ["kubectl", "get", _WF, name, "-n", self._ns, "-o", "json"],
                check=False, text=True, capture_output=True, timeout=30,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            raise SourceUnavailable("The workflow could not be read.") from exc
        if proc.returncode != 0 or not proc.stdout.strip():
            raise SourceUnavailable("The workflow could not be read.")
        try:
            item = json.loads(proc.stdout)
        except ValueError as exc:
            raise SourceUnavailable("The workflow response is invalid.") from exc
        if not isinstance(item, dict):
            raise SourceUnavailable("The workflow response is invalid.")
        return item

    def metadata_of(self, handle: str) -> WorkflowMetadata:
        meta = self._read(handle).get("metadata") or {}
        labels = meta.get("labels") or {}
        annotations = meta.get("annotations") or {}
        if not labels.get("foundry-console/run"):
            raise Conflict("The workflow is outside the console's run inventory.")
        kind = execution_kind(meta)
        if kind not in ("delivery", "maintenance", "promotion"):
            raise Conflict("The workflow execution kind is unavailable or invalid.")
        return WorkflowMetadata(
            repository=annotations.get("foundry-console/repository", ""),
            resource_version=meta.get("resourceVersion", ""), uid=meta.get("uid", ""),
            kind=kind, scratch_ref=annotations.get("foundry-console/scratch-ref", ""),
        )

    @staticmethod
    def _version(item: dict, expected_version: str | None) -> str:
        version = (item.get("metadata") or {}).get("resourceVersion")
        if not version:
            raise SourceUnavailable("The workflow's resource version is absent.")
        if expected_version is not None and version != expected_version:
            raise Conflict("The workflow changed before the command was applied.")
        return version

    def submit(self, workflow: CompiledWorkflow, *, delegated_grant_id: str | None = None) -> str:
        payload = json.loads(workflow.executor_payload)
        if (
            payload.get("metadata", {}).get("name") != workflow.name
            or payload.get("metadata", {}).get("annotations", {}).get("foundry-console/repository") != workflow.repository
            or payload.get("metadata", {}).get("labels", {}).get("foundry-console/run") != workflow.run_id
        ):
            raise ValueError("Compiled executor identity does not match its payload")
        if delegated_grant_id:
            payload["metadata"].setdefault("annotations", {})["foundry-console/delegated-grant"] = json.dumps({"grant_id": delegated_grant_id}, sort_keys=True)
        name = workflow.name
        if os.environ.get("FC_DRIVE_LIVE") != "1":
            # Not opted in to live drive: return a dry-run handle, submit nothing.
            return f"dry-run:{name}"
        proc = subprocess.run(
            ["kubectl", "create", "-f", "-", "-o", "name"],
            input=json.dumps(payload),
            check=False, text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "workflow submit failed")
        return f"live:{proc.stdout.strip()}"

    def status(self, handle: str) -> str:
        if not handle.startswith("live:"):
            return "dry-run"
        return str((self._read(handle).get("status") or {}).get("phase") or "Pending")

    def list_runs(self) -> list[RunInventoryEntry]:
        """Observe all console runs or report a source failure without inventing an empty list."""
        if os.environ.get("FC_DRIVE_LIVE") != "1":
            return []
        try:
            proc = subprocess.run(
                [
                    "kubectl",
                    "get",
                    _WF,
                    "-n",
                    self._ns,
                    "-l",
                    "foundry-console/run",
                    "-o",
                    "json",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=30,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            raise SourceUnavailable("The run inventory could not be read.") from exc
        if proc.returncode != 0 or not proc.stdout.strip():
            raise SourceUnavailable("The run inventory could not be read.")
        try:
            data = json.loads(proc.stdout)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise TypeError("Missing workflow list")
            return parse_runs(data)
        except (ValueError, TypeError, KeyError) as exc:
            raise SourceUnavailable("The run inventory response is invalid.") from exc

    def graph(self, handle: str) -> ExecutionGraph:
        """Observe one workflow graph; source failures retain their unavailable meaning."""
        if not handle.startswith("live:"):
            return ExecutionGraph("dry-run")
        return parse_graph(self._read(handle))

    def stop(self, handle: str, terminate: bool = False, reason: str = STOP_OPERATOR,
             *, expected_version: str | None = None) -> str:
        """Set shutdown and attribution with a Kubernetes resource-version precondition."""
        name = self._name(handle)
        if not name:
            return "dry-run"
        version = self._version(self._read(handle), expected_version)
        shutdown = "Terminate" if terminate else "Stop"
        proc = subprocess.run(
            ["kubectl", "patch", _WF, name, "-n", self._ns, "--type=merge",
             "-p", json.dumps({
                 "metadata": {"resourceVersion": version, "labels": {STOP_LABEL: reason}},
                 "spec": {"shutdown": shutdown},
             })], check=False, text=True, capture_output=True, timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError("The workflow shutdown was not confirmed.")
        return shutdown

    def delete(self, handle: str, *, expected_version: str, expected_uid: str) -> str:
        """Delete the exact workflow incarnation and version whose evidence was archived."""
        name = self._name(handle)
        if not name:
            return "dry-run"
        if not expected_version or not expected_uid:
            raise SourceUnavailable("Workflow deletion requires a proven version and UID.")
        url = f"/apis/argoproj.io/v1alpha1/namespaces/{quote(self._ns, safe='')}/workflows/{name}"
        options = {"apiVersion": "v1", "kind": "DeleteOptions", "propagationPolicy": "Background",
                   "preconditions": {"resourceVersion": expected_version, "uid": expected_uid}}
        proc = subprocess.run(
            ["kubectl", "delete", "--raw", url, "-f", "-"], input=json.dumps(options),
            check=False, text=True, capture_output=True, timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError("The workflow deletion was not confirmed.")
        return "deleted"

    def resume(self, handle: str, *, expected_version: str | None = None) -> str:
        """Release suspended nodes with a resource-version test in the same JSON patch."""
        name = self._name(handle)
        if not name:
            return "dry-run"
        item = self._read(handle)
        version = self._version(item, expected_version)
        ops = resume_patch(item)
        if not ops:
            return "nothing-suspended"
        patch = [{"op": "test", "path": "/metadata/resourceVersion", "value": version}, *ops]
        proc = subprocess.run(
            ["kubectl", "patch", _WF, name, "-n", self._ns, "--type=json", "-p", json.dumps(patch)],
            check=False, text=True, capture_output=True, timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError("The workflow resume was not confirmed.")
        return f"resumed:{len(ops)}"

    def logs(self, handle: str, tail: int = 400, node_id: str | None = None) -> str:
        """Run logs: every step pod's output for the workflow, each line prefixed
        [pod/<pod>/<container>], pods in start order and containers in lifecycle order with
        `main` last. Fetched one container at a time because a single all-containers read
        has no stable cross-container order: the long-terminated init/wait output would
        shuffle around the live main tail on every poll and read as new content.
        node_id scopes the read to that node's pod (the band's inspector reads one step)."""
        name = self._name(handle)
        if not name:
            return ""
        deadline = time.monotonic() + 30

        def read(args: list[str]) -> str:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceUnavailable("Workflow log capture deadline exceeded")
            try:
                result = subprocess.run(
                    args, check=False, text=True, capture_output=True, timeout=remaining
                )
            except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
                raise SourceUnavailable("Workflow log capture unavailable") from exc
            if result.returncode != 0:
                raise SourceUnavailable("Workflow log capture was not confirmed")
            if not isinstance(result.stdout, str):
                raise SourceUnavailable("Invalid workflow log response")
            return result.stdout

        listing = read([
            "kubectl", "get", "pods", "-n", self._ns,
            "-l", f"workflows.argoproj.io/workflow={name}",
            "--sort-by", ".metadata.creationTimestamp", "-o", "json",
        ])
        try:
            payload = json.loads(listing)
            pods = payload["items"]
            if not isinstance(payload, dict) or not isinstance(pods, list):
                raise TypeError("Invalid pod list")
            selected: list[tuple[str, list[str]]] = []
            for pod in pods:
                pod_name = pod["metadata"]["name"]
                if not isinstance(pod_name, str) or not pod_name:
                    raise ValueError("Missing pod identity")
                if node_id and not pod_matches_node(pod_name, node_id):
                    continue
                spec = pod["spec"]
                containers = spec["containers"]
                init = spec.get("initContainers", [])
                if not isinstance(containers, list) or not containers or not isinstance(init, list):
                    raise ValueError("Invalid pod containers")
                names = [container["name"] for container in init + containers]
                if any(not isinstance(name, str) or not name for name in names):
                    raise ValueError("Missing container identity")
                names.sort(key=lambda name: name == "main")
                selected.append((pod_name, names))
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable("Invalid workflow pod inventory") from exc
        parts: list[str] = []
        for pod_name, containers in selected:
            for container in containers:
                output = read([
                    "kubectl", "logs", pod_name, "-n", self._ns,
                    "-c", container, "--tail", str(tail),
                ])
                prefix = f"[pod/{pod_name}/{container}] "
                parts.extend(prefix + line for line in output.splitlines())
        return "\n".join(parts)

    @staticmethod
    def _name(handle: str) -> str:
        """The bare workflow name from a live handle (live:workflow.argoproj.io/<name>)."""
        if not handle.startswith("live:"):
            return ""
        match = re.fullmatch(r"live:workflows?\.argoproj\.io/([a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?)", handle)
        if match is None:
            raise ValueError("Invalid workflow handle.")
        return match.group(1)
