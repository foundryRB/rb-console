"""Promotion shared orchestration over explicit contracts."""

from __future__ import annotations


def helper_entry_environments(repo: str, installs: dict) -> dict:
    """Each install's entry environment, as far as this app can tell.

    An install declaring exactly one environment is deploying into it
    automatically, which is the whole fleet today; where a branch carries
    several, the app repo alone cannot say which one the platform writes,
    so none is excluded here and the promote act refuses at the door
    (it reads the install's own declaration).
    """
    return {
        install: environments[0]
        for install, environments in installs.items()
        if len(environments) == 1
    }
