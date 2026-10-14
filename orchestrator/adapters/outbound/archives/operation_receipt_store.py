"""Durable command receipts on the installation's persistent archive volume."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.operation_receipt import OperationReceipt


class OperationReceiptStore:
    def __init__(self, directory: Path | str):
        self.path = Path(directory) / "operation-receipts.sqlite3"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS receipts (
                    key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL, secret_write INTEGER NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '{}', result TEXT,
                    reason TEXT NOT NULL DEFAULT '')""")
                connection.execute("""CREATE TABLE IF NOT EXISTS delegated_grants (
                    grant_id TEXT PRIMARY KEY, context TEXT NOT NULL)""")
        except OSError as exc:
            raise SourceUnavailable(
                "Operation receipt storage is unavailable."
            ) from exc

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            with (
                closing(
                    sqlite3.connect(self.path, timeout=5, isolation_level=None)
                ) as connection,
                connection,
            ):
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA synchronous=FULL")
                yield connection
        except sqlite3.Error as exc:
            raise SourceUnavailable(
                "Operation receipt storage is unavailable."
            ) from exc

    @staticmethod
    def _receipt(row: sqlite3.Row) -> OperationReceipt:
        return OperationReceipt(
            key=row["key"],
            fingerprint=row["fingerprint"],
            state=row["state"],
            secret_write=bool(row["secret_write"]),
            evidence=json.loads(row["evidence"]),
            result=json.loads(row["result"]) if row["result"] is not None else None,
            reason=row["reason"],
        )

    def claim(
        self,
        key: str,
        fingerprint: str,
        *,
        authority: dict[str, str],
        secret_write: bool = False,
    ) -> tuple[OperationReceipt, bool]:
        evidence = json.dumps({"authority": authority}, sort_keys=True, allow_nan=False)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            inserted = (
                connection.execute(
                    "INSERT OR IGNORE INTO receipts(key,fingerprint,state,secret_write,evidence) VALUES(?,?,'claimed',?,?)",
                    (key, fingerprint, int(secret_write), evidence),
                ).rowcount
                == 1
            )
            row = connection.execute(
                "SELECT * FROM receipts WHERE key=?", (key,)
            ).fetchone()
            if (
                row["fingerprint"] != fingerprint
                or bool(row["secret_write"]) != secret_write
            ):
                raise Conflict(
                    "The operation key is already bound to a different request."
                )
            connection.commit()
            return self._receipt(row), inserted

    def save_grant(self, grant_id: str, context_json: dict[str, Any]) -> None:
        encoded = json.dumps(
            context_json, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO delegated_grants(grant_id,context) VALUES(?,?)",
                (grant_id, encoded),
            )
            row = connection.execute(
                "SELECT context FROM delegated_grants WHERE grant_id=?", (grant_id,)
            ).fetchone()
            if row["context"] != encoded:
                raise Conflict(
                    "The delegated grant is already bound to a different authority."
                )
            connection.commit()

    def get_grant(self, grant_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT context FROM delegated_grants WHERE grant_id=?", (grant_id,)
            ).fetchone()
            return json.loads(row["context"]) if row else None

    def get(self, key: str) -> OperationReceipt | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM receipts WHERE key=?", (key,)
            ).fetchone()
            return self._receipt(row) if row else None

    def mark_dispatched(self, key: str, evidence: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT evidence FROM receipts WHERE key=? AND state='claimed'", (key,)
            ).fetchone()
            if row is None:
                raise Conflict(
                    "Dispatch intent requires an exclusively claimed operation."
                )
            retained = json.loads(row["evidence"])
            retained.update(
                {name: value for name, value in evidence.items() if name != "authority"}
            )
            changed = connection.execute(
                "UPDATE receipts SET state='dispatched',evidence=? WHERE key=? AND state='claimed'",
                (json.dumps(retained, sort_keys=True, allow_nan=False), key),
            ).rowcount
            if changed != 1:
                raise Conflict(
                    "Dispatch intent requires an exclusively claimed operation."
                )
            connection.commit()

    def release_claim(self, key: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM receipts WHERE key=? AND state='claimed'", (key,)
            )

    def complete(self, key: str, result: Any) -> None:
        with self._connection() as connection:
            changed = connection.execute(
                "UPDATE receipts SET state='completed',result=?,reason='' WHERE key=? AND state IN ('dispatched','unknown')",
                (json.dumps(result, sort_keys=True, allow_nan=False), key),
            ).rowcount
            if changed != 1:
                raise Conflict(
                    "Completion requires a dispatched operation and authoritative evidence."
                )

    def unknown(self, key: str, reason: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE receipts SET state='unknown',reason=? WHERE key=? AND state IN ('claimed','dispatched','unknown')",
                (reason, key),
            )
