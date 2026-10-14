"""Prepare promotion projections through their actual source collectors."""

def observe_promotion(service, repo):
    collector = service.refresh.cap_refresh_metadata
    snapshot = service.promotion_state.observations.metadata.setdefault(repo, {})
    snapshot["promotion_state"] = collector.promotion.execute(repo)
    snapshot["promotion_options"] = collector.options.execute(repo)
