"""SQLite implementation of `CaseRepositoryPort` (arquitectura-v0.md, section
10). Optimistic locking: `save` only writes if the stored version still
matches `expected_version`; otherwise it raises `ConcurrencyError` without
touching the row, and the caller is responsible for reloading and re-checking
preconditions rather than blindly retrying."""

import sqlite3
from pathlib import Path

from kavak_auto_equity_agent.domain.errors import CaseNotFoundError, ConcurrencyError
from kavak_auto_equity_agent.domain.models import Case


class SQLiteCaseRepository:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def create(self, case: Case) -> Case:
        self._conn.execute(
            "INSERT INTO cases (case_id, version, data) VALUES (?, ?, ?)",
            (case.case_id, case.version, case.model_dump_json()),
        )
        self._conn.commit()
        return case

    def get(self, case_id: str) -> Case:
        row = self._conn.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise CaseNotFoundError(case_id)
        return Case.model_validate_json(row[0])

    def save(self, case: Case, expected_version: int) -> Case:
        updated = case.model_copy(update={"version": expected_version + 1})
        cursor = self._conn.execute(
            "UPDATE cases SET version = ?, data = ? WHERE case_id = ? AND version = ?",
            (updated.version, updated.model_dump_json(), case.case_id, expected_version),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            if self._conn.execute("SELECT 1 FROM cases WHERE case_id = ?", (case.case_id,)).fetchone() is None:
                raise CaseNotFoundError(case.case_id)
            raise ConcurrencyError(case.case_id, expected_version)
        return updated
