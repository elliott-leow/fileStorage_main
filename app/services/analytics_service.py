"""
Activity analytics backed by SQLite (stdlib, no dependency).

Logs four event types — ``navigate`` (folder views), ``open`` (file served),
``search`` (queries), ``preview`` (inline previews) — grouped into navigation
*sessions* by an idle timeout. Aggregations power both the dashboard and the
trajectory-aware search ranking (see ``navigation_service``).

All writes are best-effort: a logging failure must never break a request.
"""
import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

EVENT_TYPES = ("navigate", "open", "search", "preview")


def folder_of(path: Optional[str]) -> str:
    """Return the containing folder of a path ('' for root-level items)."""
    if not path:
        return ""
    return path.rsplit("/", 1)[0] if "/" in path else ""


class AnalyticsService:
    """Stores and aggregates user activity."""

    def __init__(self, db_path: str, enabled: bool = True, idle_timeout_min: int = 30):
        self.db_path = db_path
        self.enabled = enabled
        self.timeout_s = idle_timeout_min * 60
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        if self.enabled:
            try:
                self._init_db()
            except Exception as e:  # pragma: no cover - defensive
                print(f"Analytics: failed to initialize DB ({e}); disabling.")
                self.enabled = False

    # ------------------------------------------------------------------ db

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            d = os.path.dirname(self.db_path)
            if d:
                os.makedirs(d, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_ts REAL NOT NULL,
                    last_ts REAL NOT NULL,
                    client TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    session_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    path TEXT,
                    query TEXT,
                    meta TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
                CREATE INDEX IF NOT EXISTS idx_events_path ON events(path);
                CREATE INDEX IF NOT EXISTS idx_sessions_client ON sessions(client, last_ts);
                """
            )
            conn.commit()

    # ------------------------------------------------------------- logging

    def _session_for(self, conn, client: Optional[str], now: float) -> int:
        row = conn.execute(
            "SELECT id, last_ts FROM sessions WHERE client IS ? "
            "ORDER BY last_ts DESC LIMIT 1",
            (client,),
        ).fetchone()
        if row is not None and (now - row["last_ts"]) <= self.timeout_s:
            conn.execute("UPDATE sessions SET last_ts=? WHERE id=?", (now, row["id"]))
            return row["id"]
        cur = conn.execute(
            "INSERT INTO sessions (started_ts, last_ts, client) VALUES (?, ?, ?)",
            (now, now, client),
        )
        return cur.lastrowid

    def log(
        self,
        event_type: str,
        path: Optional[str] = None,
        query: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        client: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Optional[int]:
        """Record an event. Returns its session id, or None if not logged."""
        if not self.enabled or event_type not in EVENT_TYPES:
            return None
        now = time.time() if now is None else now
        meta_json = json.dumps(meta) if meta else None
        try:
            with self._lock:
                conn = self._connect()
                session_id = self._session_for(conn, client, now)
                conn.execute(
                    "INSERT INTO events (ts, session_id, type, path, query, meta) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (now, session_id, event_type, path, query, meta_json),
                )
                conn.commit()
                return session_id
        except Exception as e:  # pragma: no cover - defensive
            print(f"Analytics: log failed ({e})")
            return None

    # --------------------------------------------------------- trajectory

    def current_trajectory(
        self, client: Optional[str], now: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Ordered folder visits in the client's *active* session (else [])."""
        if not self.enabled:
            return []
        now = time.time() if now is None else now
        try:
            with self._lock:
                conn = self._connect()
                row = conn.execute(
                    "SELECT id, last_ts FROM sessions WHERE client IS ? "
                    "ORDER BY last_ts DESC LIMIT 1",
                    (client,),
                ).fetchone()
                if row is None or (now - row["last_ts"]) > self.timeout_s:
                    return []
                rows = conn.execute(
                    "SELECT path, ts FROM events WHERE session_id=? AND type='navigate' "
                    "AND path IS NOT NULL ORDER BY ts ASC",
                    (row["id"],),
                ).fetchall()
                return [{"path": r["path"], "ts": r["ts"]} for r in rows]
        except Exception:  # pragma: no cover - defensive
            return []

    def session_outcomes(self) -> List[Dict[str, Any]]:
        """
        For every session: the folders it visited and the folder of the file it
        ended up opening (the navigation 'target'). Feeds the co-occurrence model.
        """
        if not self.enabled:
            return []
        try:
            with self._lock:
                conn = self._connect()
                rows = conn.execute(
                    "SELECT session_id, type, path, ts FROM events "
                    "WHERE type IN ('navigate','open') ORDER BY session_id, ts ASC"
                ).fetchall()
        except Exception:  # pragma: no cover - defensive
            return []
        sessions: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            s = sessions.setdefault(r["session_id"], {"visited": [], "target_folder": None})
            if r["type"] == "navigate" and r["path"] is not None:
                s["visited"].append(r["path"])
            elif r["type"] == "open" and r["path"] is not None:
                s["target_folder"] = folder_of(r["path"])  # last open wins
        return list(sessions.values())

    # -------------------------------------------------------- aggregations

    def _q(self, sql: str, params=()) -> List[sqlite3.Row]:
        if not self.enabled:
            return []
        try:
            with self._lock:
                return self._connect().execute(sql, params).fetchall()
        except Exception:  # pragma: no cover - defensive
            return []

    def top_files(self, limit: int = 10, event_type: str = "open") -> List[Dict[str, Any]]:
        rows = self._q(
            "SELECT path, COUNT(*) c, MAX(ts) last FROM events "
            "WHERE type=? AND path IS NOT NULL GROUP BY path ORDER BY c DESC LIMIT ?",
            (event_type, limit),
        )
        return [{"path": r["path"], "count": r["c"], "last_ts": r["last"]} for r in rows]

    def top_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._q(
            "SELECT query, COUNT(*) c FROM events WHERE type='search' "
            "AND query IS NOT NULL AND query<>'' GROUP BY query ORDER BY c DESC LIMIT ?",
            (limit,),
        )
        return [{"query": r["query"], "count": r["c"]} for r in rows]

    def top_folders(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._q(
            "SELECT path, COUNT(*) c FROM events WHERE type='navigate' "
            "AND path IS NOT NULL GROUP BY path ORDER BY c DESC LIMIT ?",
            (limit,),
        )
        return [{"path": r["path"], "count": r["c"]} for r in rows]

    def searches_over_time(self, days: int = 30) -> List[Dict[str, Any]]:
        since = time.time() - days * 86400
        rows = self._q(
            "SELECT date(ts,'unixepoch','localtime') d, COUNT(*) c FROM events "
            "WHERE type='search' AND ts>=? GROUP BY d ORDER BY d",
            (since,),
        )
        return [{"date": r["d"], "count": r["c"]} for r in rows]

    def folder_transitions(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._q(
            "SELECT session_id, path FROM events WHERE type='navigate' "
            "AND path IS NOT NULL ORDER BY session_id, ts ASC"
        )
        counts: Dict[tuple, int] = {}
        prev_session, prev_path = None, None
        for r in rows:
            if r["session_id"] == prev_session and prev_path is not None and prev_path != r["path"]:
                key = (prev_path, r["path"])
                counts[key] = counts.get(key, 0) + 1
            prev_session, prev_path = r["session_id"], r["path"]
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [{"from": a, "to": b, "count": c} for (a, b), c in top]

    def recent_activity(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._q(
            "SELECT ts, type, path, query FROM events ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        return [
            {"ts": r["ts"], "type": r["type"], "path": r["path"], "query": r["query"]}
            for r in rows
        ]

    def file_popularity(self) -> Dict[str, Dict[str, Any]]:
        """{path: {count, last_ts}} over open+preview events, for search boosting."""
        rows = self._q(
            "SELECT path, COUNT(*) c, MAX(ts) last FROM events "
            "WHERE type IN ('open','preview') AND path IS NOT NULL GROUP BY path"
        )
        return {r["path"]: {"count": r["c"], "last_ts": r["last"]} for r in rows}

    def totals(self) -> Dict[str, int]:
        def one(sql, params=()):
            rows = self._q(sql, params)
            return rows[0][0] if rows else 0

        return {
            "opens": one("SELECT COUNT(*) FROM events WHERE type='open'"),
            "searches": one("SELECT COUNT(*) FROM events WHERE type='search'"),
            "navigates": one("SELECT COUNT(*) FROM events WHERE type='navigate'"),
            "previews": one("SELECT COUNT(*) FROM events WHERE type='preview'"),
            "unique_files": one(
                "SELECT COUNT(DISTINCT path) FROM events WHERE type IN ('open','preview')"
            ),
            "sessions": one("SELECT COUNT(*) FROM sessions"),
        }

    def summary(self) -> Dict[str, Any]:
        """Everything the dashboard needs, in one call."""
        return {
            "totals": self.totals(),
            "top_files": self.top_files(10),
            "top_queries": self.top_queries(10),
            "top_folders": self.top_folders(10),
            "searches_over_time": self.searches_over_time(30),
            "folder_transitions": self.folder_transitions(10),
            "recent_activity": self.recent_activity(20),
        }
