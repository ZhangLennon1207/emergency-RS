from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"succeeded", "partial_success", "failed"}
MUTABLE_COLUMNS = {
    "status",
    "stage",
    "progress",
    "updated_at",
    "started_at",
    "completed_at",
    "result_json",
    "errors_json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    sample_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    pre_image_path TEXT NOT NULL,
                    post_image_path TEXT NOT NULL,
                    pre_original_name TEXT NOT NULL,
                    post_original_name TEXT NOT NULL,
                    result_json TEXT,
                    errors_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(status, created_at)"
            )

    def recover_incomplete(self) -> int:
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'queued', stage = '服务重启后重新排队', progress = 0,
                    updated_at = ?, started_at = NULL
                WHERE status IN ('starting', 'running_agent1', 'running_agent2', 'assembling')
                """,
                (now,),
            )
            return int(cursor.rowcount)

    def create_job(
        self,
        *,
        job_id: str,
        sample_id: str,
        pre_image_path: Path,
        post_image_path: Path,
        pre_original_name: str,
        post_original_name: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, sample_id, status, stage, progress, created_at, updated_at,
                    pre_image_path, post_image_path, pre_original_name,
                    post_original_name, errors_json
                ) VALUES (?, ?, 'queued', '等待本地模型队列', 0, ?, ?, ?, ?, ?, ?, '[]')
                """,
                (
                    job_id,
                    sample_id,
                    now,
                    now,
                    str(pre_image_path),
                    str(post_image_path),
                    pre_original_name,
                    post_original_name,
                ),
            )
        created = self.get_job(job_id)
        if created is None:
            raise RuntimeError(f"Failed to create job {job_id}")
        return created

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def claim_next_job(self) -> dict[str, Any] | None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE jobs SET status = 'starting', stage = '准备模型任务', progress = 2,
                    updated_at = ?, started_at = COALESCE(started_at, ?)
                WHERE job_id = ?
                """,
                (now, now, row["job_id"]),
            )
            connection.commit()
        return self.get_job(str(row["job_id"]))

    def update_job(self, job_id: str, **values: Any) -> None:
        unknown = set(values) - MUTABLE_COLUMNS
        if unknown:
            raise ValueError(f"Unsupported job columns: {sorted(unknown)}")
        values.setdefault("updated_at", utc_now())
        for key in ("result_json", "errors_json"):
            if key in values and not isinstance(values[key], str):
                values[key] = json.dumps(values[key], ensure_ascii=False)
        assignments = ", ".join(f"{key} = ?" for key in values)
        parameters = [values[key] for key in values] + [job_id]
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?", parameters
            )
            if cursor.rowcount != 1:
                raise KeyError(job_id)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key, fallback in (("result_json", None), ("errors_json", [])):
            raw = result.pop(key)
            try:
                result[key.removesuffix("_json")] = json.loads(raw) if raw else fallback
            except json.JSONDecodeError:
                result[key.removesuffix("_json")] = fallback
        return result
