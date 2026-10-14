from typing import Literal

from typing_extensions import TypeAliasType

ActionKind = TypeAliasType("ActionKind", Literal["launch", "await-gate", "needs-start"])
