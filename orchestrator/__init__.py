"""The Foundry Console orchestrator.

A deterministic core: it reads a delivery repo's committed scratch (the line's
``delivery/<line-id>`` ref, mounted at ``.delivery/`` in a working checkout),
derives which phase the delivery is in and whether each gate is signed, and says
what comes next. It authors no content and runs no skill; it only checks and,
in the full service, launches a worker. See ``docs/`` for the model.
"""

__version__ = "0.1.0"
