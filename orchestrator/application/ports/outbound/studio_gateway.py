"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.app_lifecycle_result import AppLifecycleResult
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.platform_app import PlatformApp
from orchestrator.domain.model.studio_artifact import StudioArtifact
from orchestrator.domain.model.studio_health import StudioHealth

__all__ = ["StudioGateway"]


class StudioGateway(Protocol):
    def agent_catalog(self) -> list[CatalogAgent]:
        """The playbook's agent roster, read over the playbook studio's door: who the
        Console may hand a step to, with each one's posture and character. Degrades to []
        when the studio is unreachable - a run is never refused for want of a catalog."""
        ...

    def health(self) -> list[StudioHealth]:
        """Reachability plus a headline fact for each connected studio (the org-wide
        view of everything). Never raises for a single studio being down."""
        ...

    def create_app_repo(
        self, name: str, display_name: str, description: str, repo: str = ""
    ) -> None:
        """Ask platform-studio for a templated app repo: born carrying the whole
        REF-AppContract contract (thin CI caller, compose, chart, docs, intent stubs,
        commit hook), green in its own CI from the first push, with the install's
        deploy branch stood up. Raises when the studio refuses (repo exists, no
        write credential wired, studio down)."""
        ...

    def artifacts_for(self, slug: str) -> dict[str, StudioArtifact]:
        """Studio artifact status for one delivery slug, keyed by artifact identity
        (proposal->estimatekit project, design->protopane prototype, build->platform
        app). Only phases that drive a studio appear; a studio that is down yields an
        artifact with reachable=False, exists=None."""
        ...

    def platform_apps(self) -> list[PlatformApp]:
        """Available normalized applications; unavailable or malformed inventory raises SourceUnavailable."""
        ...

    def tool_url(self, studio: str) -> str:
        """The studio's east-west base URL for the gate stamper's export: where it answers
        app-to-app past the OIDC edge, the same door the cockpit's Sign hands the stamper.
        Empty for a studio this gateway does not know."""
        ...

    def playbook_repo(self) -> str:
        """The playbook's repo as an ``owner/name`` slug, asked of playbook-studio.

        The studio owns the working clone, so its upstream IS the playbook's identity -
        the one place a consumer resolves it without carrying a literal that a rename
        would silently strand. Degrades to "" when the studio is down, refuses, or
        manages no clone at all (the operator-owned local composition, which reports
        unknown rather than guessing). "" means UNKNOWN, never "no playbook": the caller
        leaves the row unmarked instead of inventing one."""
        ...

    def pause_app(self, name: str) -> AppLifecycleResult:
        """Scale a platform app to zero (a lifecycle toggle). Returns the app's new status."""
        ...

    def resume_app(self, name: str) -> AppLifecycleResult:
        """Resume a paused platform app. Returns the app's new status."""
        ...

    def estimatekit_slugs(self) -> set[str]:
        """Available estimation identities; unavailable or malformed inventory raises SourceUnavailable."""
        ...

    def protopane_slugs(self) -> set[str]:
        """Available prototype identities; unavailable or malformed inventory raises SourceUnavailable."""
        ...

    def scope_substance(self, slug: str, *, studio: str) -> dict[str, object]:
        """Normalized proposal overview, requirements, phases and estimate projection."""
        ...

    def design_substance(self, slug: str, *, studio: str) -> dict[str, object]:
        """Normalized design theme, screen markup and canvas projection."""
        ...
