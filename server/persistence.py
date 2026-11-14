"""Atomic local storage for management state; telemetry remains ephemeral."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


class StateStore:
    def __init__(self, path: str):
        self.path = path
        self.persistent = path != ":memory:"
        if not self.persistent:
            return
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = str(target)
        # State contains report/view credentials. Restrict it before SQLite writes.
        fd = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        target.chmod(0o600)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS management (id INTEGER PRIMARY KEY CHECK (id = 1), state TEXT NOT NULL)"
            )

    def load(self) -> dict | None:
        if not self.persistent:
            return None
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT state FROM management WHERE id = 1"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, state: dict) -> None:
        if self.persistent:
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute(
                    "INSERT INTO management VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state = excluded.state",
                    (json.dumps(state, allow_nan=False),),
                )
