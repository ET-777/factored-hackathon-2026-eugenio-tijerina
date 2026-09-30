"""Local SQLite storage for explicitly confirmed simulated cases only."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
from threading import RLock


MAX_PAYLOAD_BYTES = 256 * 1024


class StoreError(RuntimeError):
    """Storage failures expose fixed codes, never SQL, paths, or case contents."""


@dataclass(frozen=True)
class StoredCase:
    case_id: str
    idempotency_key: str
    owner_id: str
    kind: str
    payload_json: str
    payload_sha256: str
    state: str
    created_at: str


class CaseStore:
    """One local case store; unique keys make repeated confirmations idempotent."""

    def __init__(self, path: str | Path):
        self._lock = RLock()
        self._closed = False
        try:
            self._connection = sqlite3.connect(str(path), timeout=5, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            with self._connection:
                self._connection.execute("""
                    CREATE TABLE IF NOT EXISTS cases (
                        case_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        owner_id TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK (kind IN ('intake', 'handoff')),
                        payload_json TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state = 'recorded'),
                        created_at TEXT NOT NULL
                    )
                """)
        except (sqlite3.Error, OSError, ValueError):
            connection = getattr(self, "_connection", None)
            if connection is not None:
                connection.close()
            raise StoreError("store_open_failed") from None

    def _require_open(self) -> None:
        if self._closed:
            raise StoreError("store_closed")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._connection.close()
            except sqlite3.Error:
                raise StoreError("store_close_failed") from None
            self._closed = True

    def count(self) -> int:
        with self._lock:
            self._require_open()
            try:
                return self._connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            except sqlite3.Error:
                raise StoreError("store_read_failed") from None

    def _read(self, column: str, value: str) -> StoredCase | None:
        # column is chosen only by the two fixed methods below, never a caller.
        query = {
            "case_id": "SELECT * FROM cases WHERE case_id = ?",
            "idempotency_key": "SELECT * FROM cases WHERE idempotency_key = ?",
        }[column]
        with self._lock:
            self._require_open()
            try:
                row = self._connection.execute(query, (value,)).fetchone()
                return None if row is None else StoredCase(**dict(row))
            except sqlite3.Error:
                raise StoreError("store_read_failed") from None

    def read_by_key(self, idempotency_key: str) -> StoredCase | None:
        return self._read("idempotency_key", idempotency_key)

    def read_case(self, case_id: str) -> StoredCase | None:
        return self._read("case_id", case_id)

    def write_case(
        self, *, case_id: str, idempotency_key: str, owner_id: str,
        kind: str, payload_json: str, created_at: str,
    ) -> None:
        """Commit at most one case per key; callers must read and verify it next."""
        if (not isinstance(payload_json, str) or not payload_json
                or len(payload_json.encode("utf-8")) > MAX_PAYLOAD_BYTES
                or kind not in ("intake", "handoff")):
            raise StoreError("invalid_store_payload")
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with self._lock:
            self._require_open()
            try:
                with self._connection:
                    self._connection.execute("""
                        INSERT INTO cases
                        (case_id, idempotency_key, owner_id, kind, payload_json,
                         payload_sha256, state, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'recorded', ?)
                        ON CONFLICT(idempotency_key) DO NOTHING
                    """, (case_id, idempotency_key, owner_id, kind, payload_json, digest, created_at))
            except sqlite3.Error:
                raise StoreError("store_write_failed") from None
