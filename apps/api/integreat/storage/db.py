"""SQLite persistence (PRD FR-09): a typed document store + append-only event timeline (D-012).

Documents are Pydantic models stored as JSON, keyed by (kind, id). The `events` table is the
investigation timeline and also what the WebSocket replays to late subscribers.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from ..models import IntegreatEvent

T = TypeVar("T", bound=BaseModel)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  project_id TEXT,
  parent_id TEXT,
  data TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);
CREATE INDEX IF NOT EXISTS docs_project ON docs(kind, project_id);
CREATE INDEX IF NOT EXISTS docs_parent ON docs(kind, parent_id);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  type TEXT NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_project ON events(project_id, seq);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def put(self, kind: str, doc: BaseModel, parent_id: str | None = None) -> None:
        data = doc.model_dump_json()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO docs(kind, id, project_id, parent_id, data) VALUES (?,?,?,?,?)",
                (kind, getattr(doc, "id", None) or getattr(doc, "project_id"), getattr(doc, "project_id", None),
                 parent_id, data),
            )

    def put_many(self, kind: str, docs: list[BaseModel], parent_id: str | None = None) -> None:
        rows = [(kind, d.id, getattr(d, "project_id", None), parent_id, d.model_dump_json()) for d in docs]
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO docs(kind, id, project_id, parent_id, data) VALUES (?,?,?,?,?)", rows)

    def get(self, kind: str, id: str, cls: type[T]) -> T | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM docs WHERE kind=? AND id=?", (kind, id)).fetchone()
        return cls.model_validate_json(row[0]) if row else None

    def get_many(self, kind: str, ids: list[str], cls: type[T]) -> list[T]:
        out = [self.get(kind, i, cls) for i in ids]
        return [x for x in out if x is not None]

    def list(self, kind: str, cls: type[T], project_id: str | None = None, parent_id: str | None = None) -> list[T]:
        q, args = "SELECT data FROM docs WHERE kind=?", [kind]
        if project_id is not None:
            q += " AND project_id=?"
            args.append(project_id)
        if parent_id is not None:
            q += " AND parent_id=?"
            args.append(parent_id)
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY rowid", args).fetchall()
        return [cls.model_validate_json(r[0]) for r in rows]

    def append_event(self, ev: IntegreatEvent) -> IntegreatEvent:
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT INTO events(project_id, type, data) VALUES (?,?,?)",
                                     (ev.project_id, ev.type, "{}"))
            ev = ev.model_copy(update={"seq": cur.lastrowid})
            self._conn.execute("UPDATE events SET data=? WHERE seq=?", (ev.model_dump_json(), ev.seq))
        return ev

    def events(self, project_id: str, after_seq: int = 0, limit: int = 1000) -> list[IntegreatEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM events WHERE project_id=? AND seq>? ORDER BY seq LIMIT ?",
                (project_id, after_seq, limit)).fetchall()
        return [IntegreatEvent.model_validate(json.loads(r[0])) for r in rows]

    def delete_project(self, project_id: str) -> None:
        """Remove every document and timeline event belonging to a project. Covers docs keyed
        by project_id (runs, incidents, evidence, graph snapshots incl. versions), docs linked by
        parent_id (subsystems), and docs whose id IS the project id (project, analysis)."""
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM docs WHERE project_id=? OR parent_id=? OR id=?",
                (project_id, project_id, project_id))
            self._conn.execute("DELETE FROM events WHERE project_id=?", (project_id,))
