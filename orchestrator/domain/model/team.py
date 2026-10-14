from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    """A team of the installation: its name and the identity-provider group whose
    members belong to it."""

    name: str
    group: str
