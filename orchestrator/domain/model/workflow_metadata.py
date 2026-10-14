from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowMetadata:
    repository: str
    resource_version: str
    uid: str
    kind: str
    scratch_ref: str = ""
