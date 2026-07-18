"""
browserbot/server/db.py — SQLite metadata store manager.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browserbot.server.config import server_config


class SessionStateStore:
    """Manages local SQLite metadata cache for Pipeline sessions."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or server_config.db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrency and corruption protection
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        """Runs initial schema migrations to create sessions table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    artifact_paths_json TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def create_session(self, session_id: str, stage: str, artifact_paths: dict[str, str]) -> dict[str, Any]:
        """Creates a new session in the store."""
        now = datetime.now(timezone.utc).isoformat()
        paths_str = json.dumps(artifact_paths)
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, stage, created_at, updated_at, artifact_paths_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, stage, now, now, paths_str)
            )
            conn.commit()
        return {
            "session_id": session_id,
            "stage": stage,
            "created_at": now,
            "updated_at": now,
            "artifact_paths": artifact_paths,
        }

    def update_session(self, session_id: str, stage: str, artifact_paths: dict[str, str] | None = None) -> dict[str, Any]:
        """Updates the stage and optionally the artifact paths of a session."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            if artifact_paths is not None:
                paths_str = json.dumps(artifact_paths)
                conn.execute(
                    """
                    UPDATE sessions
                    SET stage = ?, updated_at = ?, artifact_paths_json = ?
                    WHERE id = ?
                    """,
                    (stage, now, paths_str, session_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE sessions
                    SET stage = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (stage, now, session_id)
                )
            conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieves a session from the store."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, stage, created_at, updated_at, artifact_paths_json FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
            if row:
                return {
                    "session_id": row["id"],
                    "stage": row["stage"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "artifact_paths": json.loads(row["artifact_paths_json"]),
                }
        return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """Lists all sessions in the store."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, stage, created_at, updated_at, artifact_paths_json FROM sessions ORDER BY created_at DESC"
            ).fetchall()
            return [
                {
                    "session_id": row["id"],
                    "stage": row["stage"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "artifact_paths": json.loads(row["artifact_paths_json"]),
                }
                for row in rows
            ]
