from typing import Literal

from typing_extensions import TypeAliasType

Seed = TypeAliasType("Seed", Literal["new", "follow-on", "recast", "demo", ""])
