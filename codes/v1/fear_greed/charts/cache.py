"""Last good full-history cache and immutable raw response provenance."""

import json
import sqlite3
from pathlib import Path


class HistoryCache:
    def __init__(self, database):
        path = Path(database).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=15)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS chart_history (
                source TEXT PRIMARY KEY, fetched_at TEXT NOT NULL,
                url TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chart_history_fetches (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL, fetched_at TEXT NOT NULL,
                url TEXT NOT NULL, payload TEXT NOT NULL
            );
        """)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def get(self, source):
        row = self.db.execute(
            "SELECT fetched_at, url, payload FROM chart_history WHERE source = ?", (source,)
        ).fetchone()
        return {"fetched_at": row[0], "url": row[1], "payload": json.loads(row[2])} if row else None

    def save(self, source, fetched_at, url, payload):
        raw = json.dumps(payload, allow_nan=False)
        with self.db:
            self.db.execute("INSERT INTO chart_history_fetches(source, fetched_at, url, payload) "
                            "VALUES (?, ?, ?, ?)", (source, fetched_at, url, raw))
            self.db.execute("INSERT INTO chart_history VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(source) DO UPDATE SET fetched_at=excluded.fetched_at, "
                            "url=excluded.url, payload=excluded.payload "
                            "WHERE excluded.fetched_at >= chart_history.fetched_at",
                            (source, fetched_at, url, raw))
