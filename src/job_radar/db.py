"""SQLite storage: jobs seen, their analyses, and your application pipeline.

SQLite keeps the MVP at zero setup. Moving to PostgreSQL + pgvector later only
touches this module.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from job_radar.models import Job, JobAnalysis

STATUSES = ("interested", "applied", "interviewing", "offer", "rejected", "skipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    uid TEXT PRIMARY KEY REFERENCES jobs(uid),
    data TEXT NOT NULL,
    model TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    uid TEXT PRIMARY KEY REFERENCES jobs(uid),
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "job_radar.db"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def add_jobs(self, jobs: list[Job]) -> int:
        """Inserts jobs not seen before. Returns how many were new."""
        before = self.conn.total_changes
        self.conn.executemany(
            "INSERT OR IGNORE INTO jobs (uid, data, first_seen) VALUES (?, ?, ?)",
            [(job.uid, job.model_dump_json(), _now()) for job in jobs],
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def get_job(self, uid: str) -> Job | None:
        row = self.conn.execute("SELECT data FROM jobs WHERE uid = ?", (uid,)).fetchone()
        return Job.model_validate_json(row[0]) if row else None

    def unanalyzed(self, limit: int | None = None) -> list[Job]:
        sql = (
            "SELECT j.data FROM jobs j LEFT JOIN analyses a ON a.uid = j.uid "
            "WHERE a.uid IS NULL ORDER BY j.first_seen DESC"
        )
        rows = self.conn.execute(sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()
        return [Job.model_validate_json(r[0]) for r in rows]

    def save_analysis(self, uid: str, analysis: JobAnalysis, model: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO analyses (uid, data, model, analyzed_at) VALUES (?, ?, ?, ?)",
            (uid, analysis.model_dump_json(), model, _now()),
        )
        self.conn.commit()

    def analyzed(self) -> list[tuple[Job, JobAnalysis, str | None]]:
        """Every analyzed job with its application status (None if untouched)."""
        rows = self.conn.execute(
            "SELECT j.data, a.data, p.status FROM jobs j "
            "JOIN analyses a ON a.uid = j.uid LEFT JOIN applications p ON p.uid = j.uid"
        ).fetchall()
        return [(Job.model_validate_json(j), JobAnalysis.model_validate_json(a), s) for j, a, s in rows]

    def set_status(self, uid: str, status: str, notes: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        if not self.get_job(uid):
            raise KeyError(f"unknown job {uid}")
        self.conn.execute(
            "INSERT OR REPLACE INTO applications (uid, status, notes, updated_at) VALUES (?, ?, ?, ?)",
            (uid, status, notes, _now()),
        )
        self.conn.commit()

    def pipeline(self) -> list[tuple[str, str, str, str, str]]:
        """(uid, company, title, status, updated_at) for every tracked job."""
        rows = self.conn.execute(
            "SELECT p.uid, j.data, p.status, p.updated_at FROM applications p "
            "JOIN jobs j ON j.uid = p.uid ORDER BY p.updated_at DESC"
        ).fetchall()
        out = []
        for uid, data, status, updated in rows:
            job = Job.model_validate_json(data)
            out.append((uid, job.company, job.title, status, updated))
        return out
