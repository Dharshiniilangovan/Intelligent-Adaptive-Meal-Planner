"""Persistent, expiring JSON cache for external grocery lookups."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "grocery_cache.db"


def cache_key(category, payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((category + ":" + canonical).encode("utf-8")).hexdigest()


class PersistentCache:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("GC1_CACHE_PATH") or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (category TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL, PRIMARY KEY(category, key))")

    from contextlib import contextmanager

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            with db:
                yield db
        finally:
            db.close()

    def get(self, category, key):
        with self._connect() as db:
            row = db.execute("SELECT value, expires_at FROM cache WHERE category=? AND key=?", (category, key)).fetchone()
            if row is None:
                return None
            if row[1] <= time.time():
                db.execute("DELETE FROM cache WHERE category=? AND key=?", (category, key))
                return None
            try:
                return json.loads(row[0])
            except (ValueError, TypeError):
                db.execute("DELETE FROM cache WHERE category=? AND key=?", (category, key))
                return None

    def set(self, category, key, value, ttl_seconds):
        if ttl_seconds <= 0:
            return
        encoded = json.dumps(value, allow_nan=False)
        now = time.time()
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?)", (category, key, encoded, now, now + ttl_seconds))

    def delete(self, category, key):
        with self._connect() as db:
            db.execute("DELETE FROM cache WHERE category=? AND key=?", (category, key))

    def clear_expired(self):
        with self._connect() as db:
            return db.execute("DELETE FROM cache WHERE expires_at<=?", (time.time(),)).rowcount

    def export_json(self, destination):
        with self._connect() as db:
            rows = db.execute("SELECT category, key, value, created_at, expires_at FROM cache WHERE expires_at>? ORDER BY category, key", (time.time(),)).fetchall()
        result = [{"category": c, "key": k, "value": json.loads(v), "created_at": created, "expires_at": expires} for c, k, v, created, expires in rows]
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return len(result)
