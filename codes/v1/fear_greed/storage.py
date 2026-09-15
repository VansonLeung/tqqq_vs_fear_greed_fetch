"""SQLite observations, provenance, and persistent events; no delivery state."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .rules import entry_event

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    observed_at TEXT PRIMARY KEY,
    observation TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    observed_at TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    attempted_at TEXT NOT NULL,
    fetch_status TEXT NOT NULL,
    payload TEXT,
    issues TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=15, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f"Unsupported database schema version: {version}")
            self.connection.executescript(SCHEMA)
            self.connection.execute("PRAGMA user_version = 1")
        except Exception:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def latest(self):
        return self.connection.execute(
            "SELECT * FROM observations ORDER BY observed_at DESC LIMIT 1"
        ).fetchone()

    def previous(self, timestamp: str):
        row = self.connection.execute(
            "SELECT observation FROM observations WHERE accepted = 1 AND observed_at < ? "
            "ORDER BY observed_at DESC LIMIT 1", (timestamp,),
        ).fetchone()
        return json.loads(row["observation"]) if row else None

    def event(self, timestamp: str):
        row = self.connection.execute(
            "SELECT sequence, body FROM events WHERE observed_at = ?", (timestamp,)
        ).fetchone()
        return dict(json.loads(row["body"]), sequence=row["sequence"]) if row else None

    def save_observation(self, observation: dict, fetched_at: str, current: bool) -> bool:
        """Caller excludes older observations and same-timestamp revisions."""
        timestamp = observation["observed_at"]
        existing = self.connection.execute(
            "SELECT accepted FROM observations WHERE observed_at = ?", (timestamp,)
        ).fetchone()
        newly_accepted = current and (existing is None or not existing["accepted"])
        self.connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?) ON CONFLICT(observed_at) "
            "DO UPDATE SET fetched_at = MAX(observations.fetched_at, excluded.fetched_at), "
            "accepted = MAX(observations.accepted, excluded.accepted)",
            (timestamp, json.dumps(observation), fetched_at, int(current)),
        )
        if newly_accepted and existing is None:
            event = entry_event(self.previous(timestamp), observation)
            if event:
                self.connection.execute(
                    "INSERT INTO events(event_id, observed_at, body) VALUES (?, ?, ?)",
                    (event["event_id"], timestamp, json.dumps(event)),
                )
        return newly_accepted

    def save_attempt(self, now: str, status: str, payload, issues: list):
        self.connection.execute(
            "INSERT INTO attempts(attempted_at, fetch_status, payload, issues) VALUES (?, ?, ?, ?)",
            (now, status, json.dumps(payload) if payload is not None else None, json.dumps(issues)),
        )


def read_events(database: Path, after_sequence: int = 0) -> list[dict]:
    """Replay events after a caller-owned delivery cursor; never acknowledge sends."""
    if after_sequence < 0:
        raise ValueError("after_sequence must be nonnegative")
    with Store(database) as store:
        rows = store.connection.execute(
            "SELECT sequence, body FROM events WHERE sequence > ? ORDER BY sequence",
            (after_sequence,),
        ).fetchall()
        return [dict(json.loads(row["body"]), sequence=row["sequence"]) for row in rows]
