from typing import Literal

from typing_extensions import TypeAliasType

DeliveryStatus = TypeAliasType(
    "DeliveryStatus",
    Literal[
        "not-a-delivery",
        "run-phase",
        "awaiting-gate",
        "delivered",
        "learned",
        "degraded",
        "loading",
        "unavailable",
    ],
)
