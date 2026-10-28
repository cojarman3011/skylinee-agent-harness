"""Single-operator persistent state. SQLite transactions protect schedule claims."""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS objects (kind TEXT, id TEXT, data TEXT, PRIMARY KEY(kind,id))"
        )
        self.db.commit()
        self.lock = threading.RLock()

    def close(self):
        self.db.close()

    def put(self, kind, obj):
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO objects VALUES (?,?,?)",
                (kind, obj["id"], json.dumps(obj)),
            )
            self.db.commit()
        return obj

    def new(self, kind, **fields):
        return self.put(
            kind, {"id": uuid.uuid4().hex, "created_at": time.time(), **fields}
        )

    def get(self, kind, ident):
        with self.lock:
            row = self.db.execute(
                "SELECT data FROM objects WHERE kind=? AND id=?", (kind, ident)
            ).fetchone()
        if row is None:
            raise KeyError(ident)
        return json.loads(row[0])

    def list(self, kind, limit=200):
        with self.lock:
            query = "SELECT data FROM objects WHERE kind=? ORDER BY rowid DESC"
            rows = self.db.execute(
                query + (" LIMIT ?" if limit is not None else ""),
                (kind, limit) if limit is not None else (kind,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def remove(self, kind, ident):
        with self.lock:
            self.db.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, ident))
            self.db.commit()

    def claim_schedule(self, ident, now):
        """Advance the next due time atomically; no missed-run catch-up flood."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT data FROM objects WHERE kind=? AND id=?",
                    ("schedule", ident),
                ).fetchone()
                obj = json.loads(row[0]) if row else None
                if not obj or not obj["enabled"] or obj["next_run"] > now:
                    self.db.rollback()
                    return None
                obj["next_run"] = now + obj["interval_seconds"]
                self.db.execute(
                    "UPDATE objects SET data=? WHERE kind=? AND id=?",
                    (json.dumps(obj), "schedule", ident),
                )
                self.db.commit()
                return obj
            except BaseException:
                self.db.rollback()
                raise

    def search(self, kind, query, fields, limit=10):
        tokens = query.lower().split()[:12]
        found = []
        for obj in self.list(kind, 2000):
            text = " ".join(str(obj.get(f, "")) for f in fields).lower()
            score = sum(t in text for t in tokens)
            if score or not tokens:
                found.append((score, obj))
        return [o for _, o in sorted(found, key=lambda x: x[0], reverse=True)[:limit]]
