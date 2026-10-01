"""SQLite implementation of `AuditLogPort` and its PII masking (arquitectura-v0.md,
sections 5 and 9). Append-only: there is no update or delete here. Before a
row is written, `mask_pii` replaces any RFC found inside `input`/`output` with
a partially hidden form, e.g. `PEGJ800101AB1` -> `PEGJ******AB1`."""

import re
import sqlite3
from pathlib import Path
from typing import Any

from kavak_auto_equity_agent.domain.ports import AuditEntry

# Mexican RFC: 3 letters (moral) or 4 letters (fisica), 6-digit date, 3-char homoclave.
_RFC_PATTERN = re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b")


def _mask_rfc(token: str) -> str:
    head_len = len(token) - 9
    return token[:head_len] + "*" * 6 + token[-3:]


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return _RFC_PATTERN.sub(lambda match: _mask_rfc(match.group(0)), value)
    if isinstance(value, dict):
        return {key: _mask_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    return value


def mask_pii(entry: AuditEntry) -> AuditEntry:
    return entry.model_copy(
        update={
            "input": _mask_value(entry.input),
            "output": _mask_value(entry.output) if entry.output is not None else None,
        }
    )


class SQLiteAuditLog:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record(self, entry: AuditEntry) -> None:
        masked = mask_pii(entry)
        self._conn.execute(
            "INSERT INTO audit_log (case_id, data) VALUES (?, ?)",
            (masked.case_id, masked.model_dump_json()),
        )
        self._conn.commit()

    def list_for_case(self, case_id: str) -> list[AuditEntry]:
        rows = self._conn.execute(
            "SELECT data FROM audit_log WHERE case_id = ? ORDER BY id", (case_id,)
        ).fetchall()
        return [AuditEntry.model_validate_json(row[0]) for row in rows]

    def list_all(self) -> list[AuditEntry]:
        rows = self._conn.execute("SELECT data FROM audit_log ORDER BY id").fetchall()
        return [AuditEntry.model_validate_json(row[0]) for row in rows]
