"""Semantic fixture builders from repository wire examples."""
from orchestrator.adapters.outbound.github import maintenance_evidence as wire
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue


def semantic_issue(value) -> MaintenanceIssue:
    return value if isinstance(value, MaintenanceIssue) else wire.issue(value)

from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest


def semantic_pr(value) -> MaintenancePullRequest:
    return value if isinstance(value, MaintenancePullRequest) else wire.pull_request(value)

from orchestrator.domain.model.maintenance_review import MaintenanceReview


def semantic_review(value) -> MaintenanceReview:
    return value if isinstance(value, MaintenanceReview) else wire.review(value)

from orchestrator.domain.model.maintenance_check import MaintenanceCheck


def semantic_check(value) -> MaintenanceCheck:
    return value if isinstance(value, MaintenanceCheck) else wire.check(value)

from orchestrator.domain.model.maintenance_file import MaintenanceFile


def semantic_file(value) -> MaintenanceFile:
    return value if isinstance(value, MaintenanceFile) else wire.changed_file(value)

from orchestrator.domain.model.maintenance_release import MaintenanceRelease


def semantic_release(value) -> MaintenanceRelease:
    return value if isinstance(value, MaintenanceRelease) else wire.release(value)

from orchestrator.domain.model.maintenance_comment import MaintenanceComment


def semantic_comment(value) -> MaintenanceComment:
    return value if isinstance(value, MaintenanceComment) else wire.comment(value)
