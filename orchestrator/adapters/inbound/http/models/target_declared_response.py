from orchestrator.adapters.inbound.http.models.promotion_state import PromotionState


class TargetDeclaredResponse(PromotionState):
    target: str
    commit: str
