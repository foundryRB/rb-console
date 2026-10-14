"""Run-history helpers: pure pod/line matching for node-scoped log reads, shared by the
executor adapter (which picks which live pods to read) and the service (which filters a
completed run's snapshot the same way). Both sources speak the port's "pod-prefixed tail"
format: every line starts ``[pod/<pod>/<container>] ``.
"""

from __future__ import annotations

_PREFIX = "[pod/"


def pod_matches_node(pod_name: str, node_id: str) -> bool:
    """True when a pod belongs to a workflow node. Argo names a node's pod either exactly
    as the node id (v1 pod names) or ``<workflow>-<template>-<suffix>`` where ``<suffix>``
    is the node id's trailing token (v2 pod names, the modern default) - match on either."""
    if not pod_name or not node_id:
        return False
    if pod_name == node_id:
        return True
    suffix = node_id.rsplit("-", 1)[-1]
    return bool(suffix) and pod_name.endswith(f"-{suffix}")


def filter_node_lines(text: str, node_id: str) -> str:
    """Only one node's lines from a pod-prefixed log text: the lines whose ``[pod/...]``
    prefix names a pod of that node. Lines without the prefix carry no pod identity and
    are dropped - a node-scoped read never guesses."""
    kept: list[str] = []
    for line in text.splitlines():
        if not line.startswith(_PREFIX):
            continue
        pod = line[len(_PREFIX) :].split("/", 1)[0]
        if pod_matches_node(pod, node_id):
            kept.append(line)
    return "\n".join(kept)
