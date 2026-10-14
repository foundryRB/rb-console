"""Independent observation ticks with cancellation and visible failures."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import FastAPI

from orchestrator.application.ports.inbound.console import ConsoleCapabilities
from orchestrator.application.services.projections.observation_schedule import (
    OBSERVATION_INTERVAL,
)


def build_lifespan(capabilities: ConsoleCapabilities):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def observe() -> None:
            while True:
                try:
                    await asyncio.to_thread(capabilities.refresh.execute)
                except Exception:
                    logging.getLogger(__name__).exception("Observation tick failed")
                finally:
                    app.state.ready = True
                await asyncio.sleep(OBSERVATION_INTERVAL.total_seconds())

        async def reconcile() -> None:
            while True:
                for row in capabilities.runs.execute():
                    grant = row.grant_id
                    if not grant:
                        continue
                    try:
                        repo = str(row.repository or "")
                        if not repo:
                            continue
                        context = capabilities.resolve_delegated_grant.execute(
                            grant, repo
                        )
                        identity = f"{context.grant_id}:{row.handle}:{row.phase}:{datetime.now(UTC).isoformat(timespec='minutes')}"
                        await asyncio.to_thread(
                            capabilities.reconcile_maintenance_runs.execute,
                            repo,
                            context=context,
                            operation_id=sha256(identity.encode()).hexdigest(),
                        )
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Delegated reconciliation failed"
                        )
                await asyncio.sleep(120)

        task = asyncio.create_task(observe(), name="index-observations")
        command_task = asyncio.create_task(
            reconcile(), name="authorized-maintenance-reconciliation"
        )
        try:
            yield
        finally:
            task.cancel()
            command_task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            try:
                await command_task
            except asyncio.CancelledError:
                pass

    return lifespan
