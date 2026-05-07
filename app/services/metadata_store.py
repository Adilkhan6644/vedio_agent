from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class UploadMetadataStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    job_id TEXT PRIMARY KEY,
                    generated_video_id TEXT,
                    source_url TEXT,
                    source_file TEXT,
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create_job(
        self,
        job_id: str,
        generated_video_id: str | None,
        source_url: str | None,
        source_file: str | None,
        metadata: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO uploads (
                    job_id, generated_video_id, source_url, source_file, status,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    generated_video_id,
                    source_url,
                    source_file,
                    "queued",
                    json.dumps(metadata),
                    now,
                    now,
                ),
            )

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        error_message: str | None = None,
        retry_count: int | None = None,
        youtube_video_id: str | None = None,
        youtube_url: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            fields = ["status = ?", "updated_at = ?"]
            values: list[Any] = [status, now]

            if error_message is not None:
                fields.append("error_message = ?")
                values.append(error_message)
            if retry_count is not None:
                fields.append("retry_count = ?")
                values.append(retry_count)
            if youtube_video_id is not None:
                fields.append("youtube_video_id = ?")
                values.append(youtube_video_id)
            if youtube_url is not None:
                fields.append("youtube_url = ?")
                values.append(youtube_url)

            values.append(job_id)
            conn.execute(f"UPDATE uploads SET {', '.join(fields)} WHERE job_id = ?", values)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            cursor = conn.execute(
                """
                SELECT job_id, generated_video_id, source_url, source_file, youtube_video_id,
                       youtube_url, status, error_message, retry_count,
                       metadata_json, created_at, updated_at
                FROM uploads
                WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "job_id": row[0],
            "generated_video_id": row[1],
            "source_url": row[2],
            "source_file": row[3],
            "youtube_video_id": row[4],
            "youtube_url": row[5],
            "status": row[6],
            "error_message": row[7],
            "retry_count": row[8],
            "metadata": json.loads(row[9]) if row[9] else {},
            "created_at": row[10],
            "updated_at": row[11],
        }
