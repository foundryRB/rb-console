"""Target settings own model and timeout values beside committed line policy."""

from pytest_intent import intent

from orchestrator.adapters.outbound.settings.in_memory_config_store import (
    InMemoryConfigStore,
)
from orchestrator.application.use_cases.projections.collect_delivery_config import (
    CollectDeliveryConfig,
)


class LinePolicy:
    def read_config(self, repo):
        return {
            "mode": "one-shot",
            "agent": "other-agent",
            "provider": "other-provider",
            "model": "other-model",
            "base_url": "https://other.example",
            "timeout_seconds": 99,
        }


@intent("INT-FC-R45")
def test_target_settings_are_authoritative_and_line_mode_is_retained():
    settings = InMemoryConfigStore()
    collector = CollectDeliveryConfig(
        config=settings, credentials=None, source=LinePolicy()
    )
    result = collector.execute("org/app")
    assert result["mode"] == "one-shot"
    assert (
        result["agent"],
        result["provider"],
        result["model"],
        result["base_url"],
    ) == ("", "claude", "", "")
    assert result["timeout_seconds"] == 3600
    settings.put_setting(
        "target-app",
        {
            "agent": "selected-agent",
            "provider": "selected-provider",
            "model": "selected-model",
            "timeout_seconds": "1800",
        },
        None,
    )
    result = collector.execute("org/app")
    assert (
        result["agent"],
        result["provider"],
        result["model"],
        result["timeout_seconds"],
    ) == ("selected-agent", "selected-provider", "selected-model", 1800)
    assert result["mode"] == "one-shot"
