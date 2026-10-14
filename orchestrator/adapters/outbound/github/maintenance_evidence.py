"""Normalize GitHub wire records at the repository adapter boundary."""

from collections.abc import Mapping

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.maintenance_check import MaintenanceCheck
from orchestrator.domain.model.maintenance_comment import MaintenanceComment
from orchestrator.domain.model.maintenance_file import MaintenanceFile
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.maintenance_release import MaintenanceRelease
from orchestrator.domain.model.maintenance_review import MaintenanceReview


def _record(data: object) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise SourceUnavailable("Invalid repository evidence record")
    return data


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SourceUnavailable("Invalid repository evidence text")
    return value


def _object(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    return {} if value is None else _record(value)


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourceUnavailable("Invalid repository evidence number")
    return value


def _list(data: Mapping[str, object], key: str) -> list:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SourceUnavailable("Invalid repository evidence collection")
    return value


def issue(data) -> MaintenanceIssue:
    data = _record(data)
    labels = _list(data, "labels")
    return MaintenanceIssue(
        number=_integer(data, "number"),
        title=_text(data, "title"),
        body=_text(data, "body"),
        author=_text(_object(data, "user"), "login"),
        labels=tuple(
            _text(_record(label), "name")
            if isinstance(label, Mapping)
            else _text({"label": label}, "label")
            for label in labels
        ),
        url=_text(data, "html_url"),
        created_at=_text(data, "created_at"),
        issue_type=_text(_object(data, "type"), "name"),
        is_pull_request="pull_request" in data,
        state=_text(data, "state") or "open",
    )


def review(data) -> MaintenanceReview:
    data = _record(data)
    return MaintenanceReview(
        author=_text(_object(data, "user"), "login"),
        association=_text(data, "author_association"),
        state=_text(data, "state"),
        body=_text(data, "body"),
        submitted_at=_text(data, "submitted_at"),
    )


def check(data) -> MaintenanceCheck:
    data = _record(data)
    return MaintenanceCheck(
        status=_text(data, "status"),
        conclusion=_text(data, "conclusion") or None,
        name=_text(data, "name"),
    )


def pull_request(data) -> MaintenancePullRequest:
    data = _record(data)
    head = _object(data, "head")
    return MaintenancePullRequest(
        number=_integer(data, "number"),
        title=_text(data, "title"),
        body=_text(data, "body"),
        author=_text(_object(data, "user"), "login"),
        head_branch=_text(head, "ref"),
        head_sha=_text(head, "sha"),
        url=_text(data, "html_url"),
        updated_at=_text(data, "updated_at"),
        state=_text(data, "state") or "open",
        merged=bool(data.get("merged_at") or data.get("merged")),
        reviews=tuple(review(r) for r in _list(data, "reviews")),
        checks=tuple(check(c) for c in _list(data, "check_runs")),
    )


def changed_file(data) -> MaintenanceFile:
    data = _record(data)
    return MaintenanceFile(
        filename=_text(data, "filename"),
        status=_text(data, "status"),
        additions=_integer(data, "additions"),
        deletions=_integer(data, "deletions"),
        patch=_text(data, "patch"),
    )


def release(data) -> MaintenanceRelease:
    data = _record(data)
    return MaintenanceRelease(
        tag=_text(data, "tag_name"),
        name=_text(data, "name"),
        published_at=_text(data, "published_at"),
        url=_text(data, "html_url"),
    )


def comment(data) -> MaintenanceComment:
    return MaintenanceComment(body=_text(_record(data), "body"))
