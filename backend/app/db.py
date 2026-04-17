from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import from_json, to_json, utcnow


class MetadataDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    params_json TEXT NOT NULL,
                    layer_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS layers (
                    id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    path TEXT NOT NULL,
                    bounds_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(scene_id, params_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_layers_scene_hash ON layers(scene_id, params_hash);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                """
            )
            conn.commit()

    def create_job(self, scene_id: str, params: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        now = utcnow().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(id, scene_id, status, progress, params_json, layer_id, error, created_at, updated_at)
                VALUES(?, ?, 'queued', 0.0, ?, NULL, NULL, ?, ?)
                """,
                (job_id, scene_id, to_json(params), now, now),
            )
            conn.commit()
        return job_id

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        layer_id: str | None = None,
        error: str | None = None,
    ) -> None:
        now = utcnow().isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown job_id={job_id}")
            conn.execute(
                """
                UPDATE jobs
                SET status=?, progress=?, layer_id=?, error=?, updated_at=?
                WHERE id=?
                """,
                (
                    status if status is not None else row["status"],
                    float(progress if progress is not None else row["progress"]),
                    layer_id if layer_id is not None else row["layer_id"],
                    error if error is not None else row["error"],
                    now,
                    job_id,
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "scene_id": row["scene_id"],
            "status": row["status"],
            "progress": float(row["progress"]),
            "params": from_json(row["params_json"]),
            "layer_id": row["layer_id"],
            "error": row["error"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }

    def upsert_layer(
        self,
        *,
        layer_id: str,
        scene_id: str,
        params_hash: str,
        path: str,
        bounds: list[float],
        summary: dict[str, Any],
    ) -> None:
        now = utcnow().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO layers(id, scene_id, params_hash, path, bounds_json, summary_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_id, params_hash) DO UPDATE SET
                    id=excluded.id,
                    path=excluded.path,
                    bounds_json=excluded.bounds_json,
                    summary_json=excluded.summary_json,
                    created_at=excluded.created_at
                """,
                (layer_id, scene_id, params_hash, path, to_json({"bounds": bounds}), to_json(summary), now),
            )
            conn.commit()

    def get_layer_by_id(self, layer_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM layers WHERE id=?", (layer_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "scene_id": row["scene_id"],
            "params_hash": row["params_hash"],
            "path": row["path"],
            "bounds": from_json(row["bounds_json"]).get("bounds", []),
            "summary": from_json(row["summary_json"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
        }

    def get_cached_layer(self, scene_id: str, params_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM layers WHERE scene_id=? AND params_hash=?",
                (scene_id, params_hash),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "scene_id": row["scene_id"],
            "params_hash": row["params_hash"],
            "path": row["path"],
            "bounds": from_json(row["bounds_json"]).get("bounds", []),
            "summary": from_json(row["summary_json"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
        }
