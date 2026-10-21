"""Local SQLite preview state only; never imports an application DB client."""

import json
from pathlib import Path
import sqlite3

from .contracts import SnapshotEvent, projection
from .errors import IntegrationError


class PreviewStore:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            target = Path(path)
            if target.suffix != ".sqlite3":
                raise IntegrationError("preview_state_requires_sqlite3_suffix")
            target.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        tables = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {"preview_receipts", "preview_messages"}:
            self.close()
            raise IntegrationError("unrecognized_preview_state")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.close()
            raise IntegrationError("unsupported_preview_state_version")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS preview_receipts (
                workspace_id TEXT NOT NULL, event_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                PRIMARY KEY (workspace_id, event_id));
            CREATE TABLE IF NOT EXISTS preview_messages (
                workspace_id TEXT NOT NULL, message_id TEXT NOT NULL, revision INTEGER NOT NULL,
                fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY (workspace_id, message_id));
            PRAGMA user_version=1;
        """)

    def apply(self, event: SnapshotEvent) -> str:
        with self.connection:
            receipt = self.connection.execute(
                "SELECT fingerprint FROM preview_receipts WHERE workspace_id=? AND event_id=?",
                (event.workspace_id, event.event_id)).fetchone()
            if receipt:
                if receipt[0] != event.fingerprint:
                    raise IntegrationError("event_id_conflict")
                return "duplicate"
            previous = self.connection.execute(
                "SELECT revision, fingerprint FROM preview_messages WHERE workspace_id=? AND message_id=?",
                (event.workspace_id, event.message_id)).fetchone()
            outcome = "applied"
            if previous:
                if event.revision < previous[0]:
                    outcome = "stale"
                elif event.revision == previous[0]:
                    if previous[1] != event.message_fingerprint:
                        raise IntegrationError("revision_conflict")
                    outcome = "unchanged"
            if outcome == "applied":
                self.connection.execute("""
                    INSERT INTO preview_messages VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, message_id) DO UPDATE SET
                      revision=excluded.revision, fingerprint=excluded.fingerprint, snapshot=excluded.snapshot
                """, (event.workspace_id, event.message_id, event.revision,
                      event.message_fingerprint, json.dumps(projection(event), ensure_ascii=False)))
            self.connection.execute("INSERT INTO preview_receipts VALUES (?, ?, ?)",
                                    (event.workspace_id, event.event_id, event.fingerprint))
            return outcome

    def snapshots(self):
        return [json.loads(row[0]) for row in self.connection.execute(
            "SELECT snapshot FROM preview_messages ORDER BY workspace_id, message_id")]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
