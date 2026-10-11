"""SQLite-backed fact store with entity resolution and trust scoring.

Vendored from hermes-agent-main plugins/memory/holographic/store.py and adapted for
xiaozhi-server:

- hermes-only helpers (``hermes_state_wal.apply_wal_with_fallback``,
  ``hermes_cli.sqlite_util.add_column_if_missing``) are inlined as plain PRAGMA logic
  with the same fail-soft behavior.
- ``facts`` gains ``status`` (active/rejected), ``agent_id``, ``device_id``,
  ``session_id`` columns; rejected facts are excluded from retrieval in
  ``retrieval.py`` and can only be restored via the review workflow.
- Admin-side operations added: ``set_fact_status`` / ``update_fact_trust`` /
  ``set_fact_sources`` plus paginated / FTS / filtered admin queries.

Core storage semantics (content UNIQUE idempotency, trust clamping, entity
extraction, per-category HRR memory banks, shared-connection registry) are kept
identical to the upstream implementation.
"""

import os
import re
import sqlite3
import threading
from pathlib import Path

from . import holographic as hrr

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT NOT NULL UNIQUE,
    category        TEXT DEFAULT 'general',
    tags            TEXT DEFAULT '',
    trust_score     REAL DEFAULT 0.5,
    status          TEXT DEFAULT 'active',
    agent_id        TEXT DEFAULT '',
    device_id       TEXT DEFAULT '',
    session_id      TEXT DEFAULT '',
    retrieval_count INTEGER DEFAULT 0,
    helpful_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hrr_vector      BLOB
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    entity_type TEXT DEFAULT 'unknown',
    aliases     TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_entities (
    fact_id   INTEGER REFERENCES facts(fact_id),
    entity_id INTEGER REFERENCES entities(entity_id),
    PRIMARY KEY (fact_id, entity_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
    USING fts5(content, tags, content=facts, content_rowid=fact_id);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, tags)
        VALUES (new.fact_id, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, tags)
        VALUES ('delete', old.fact_id, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, tags)
        VALUES ('delete', old.fact_id, old.content, old.tags);
    INSERT INTO facts_fts(rowid, content, tags)
        VALUES (new.fact_id, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS memory_banks (
    bank_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name  TEXT NOT NULL UNIQUE,
    vector     BLOB NOT NULL,
    dim        INTEGER NOT NULL,
    fact_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Indexes live in a separate script: they reference the new columns (status, agent_id), so on a
# legacy hermes DB they must only be created AFTER the ALTER TABLE backfill below.
_SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_facts_trust    ON facts(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_status   ON facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_agent    ON facts(agent_id);
CREATE INDEX IF NOT EXISTS idx_entities_name  ON entities(name);
"""

_CREATE_MEMORY_TIMES = """
CREATE TABLE IF NOT EXISTS memory_times (
    memory_id      INTEGER NOT NULL,
    time_reference TEXT    NOT NULL,
    actual_date    TIMESTAMP,
    PRIMARY KEY (memory_id, time_reference),
    FOREIGN KEY (memory_id) REFERENCES facts(fact_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_memory_times_ref ON memory_times(time_reference);
CREATE INDEX IF NOT EXISTS idx_memory_times_date ON memory_times(actual_date);
"""
_HELPFUL_DELTA, _UNHELPFUL_DELTA = 0.05, -0.10

# Entity extraction patterns, applied in order: capitalized multi-word phrases ("John Doe"), double-quoted terms,
# single-quoted terms, then "X aka Y" (both sides).
_RE_SINGLE_ENTITY = (re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'), re.compile(r'"([^"]+)"'), re.compile(r"'([^']+)'"))
_RE_AKA = re.compile(r'(\w+(?:\s+\w+)*)\s+(?:aka|also known as)\s+(\w+(?:\s+\w+)*)', re.IGNORECASE)
_ENTITY_NAMES_SQL = "SELECT e.name FROM entities e JOIN fact_entities fe ON fe.entity_id = e.entity_id WHERE fe.fact_id = ?"
# Entity lookup order: exact name, then aliases (comma-separated; wrapped in commas for whole-alias matching).
_ENTITY_LOOKUPS = ("SELECT entity_id FROM entities WHERE name LIKE ?",
                   "SELECT entity_id FROM entities WHERE ',' || aliases || ',' LIKE '%,' || ? || ',%'")

_FACT_PUBLIC_COLUMNS = ("fact_id, content, category, tags, trust_score, status, agent_id, device_id, session_id, "
                        "retrieval_count, helpful_count, created_at, updated_at")


def _clamp_trust(value: float) -> float:
    return max(0.0, min(1.0, value))


def _like_escape(value: str) -> str:
    """Escape LIKE wildcards for use with ESCAPE '\\' (mirrors retrieval._merge_like_candidates)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MemoryStore:
    """SQLite-backed fact store with entity resolution and trust scoring.

    Process-wide shared connection registry: SQLite allows one writer at a time and several providers
    coexist per process (main agent + every delegate_task subagent), so all instances for the same database
    share ONE connection and ONE re-entrant lock — writes are fully serialized and "database is locked" is
    impossible. Refcounted: closing one instance never tears the connection out from under a sibling."""

    _shared: dict = {}
    _shared_guard = threading.Lock()

    def __init__(self, db_path: "str | Path | None" = None, default_trust: float = 0.5, hrr_dim: int = 1024) -> None:
        if db_path is None:
            raise ValueError("db_path is required (xiaozhi keeps one SQLite file per agent)")
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_trust, self.hrr_dim, self._hrr_available = _clamp_trust(default_trust), hrr_dim, hrr._HAS_NUMPY
        try:  # resolve() so symlinked/relative paths to the same file share ONE connection
            self._key = str(self.db_path.resolve())
        except OSError:
            self._key = str(self.db_path)
        with MemoryStore._shared_guard:
            entry = MemoryStore._shared.get(self._key)
            if entry is None:
                # Autocommit: a write that raises mid-method can't leave a dangling transaction (and its
                # write lock) open; the explicit commit() calls in _write are then harmless no-ops.
                conn = sqlite3.connect(self._key, check_same_thread=False, timeout=10.0, isolation_level=None)
                conn.row_factory = sqlite3.Row
                entry = MemoryStore._shared[self._key] = {"conn": conn, "lock": threading.RLock(), "refs": 0, "ready": False}
            entry["refs"] += 1
            self._entry, self._conn, self._lock = entry, entry["conn"], entry["lock"]
        with self._lock:  # schema initialised once per shared connection
            if not entry["ready"]:
                self._init_db()
                entry["ready"] = True

    def _init_db(self) -> None:
        """Create schema and enable WAL inline (hermes helper removed). Shared/network filesystems may not
        support WAL — degrade to the default journal mode with a warning, exactly like the original helper."""
        try:
            journal_mode = self._one("PRAGMA journal_mode=WAL")[0]
            if str(journal_mode).lower() != "wal":
                self._conn.execute("PRAGMA journal_mode=DELETE")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=10000")
        except sqlite3.DatabaseError as e:
            print(f"[holographic] WAL setup failed for {self._key}, using default journal mode: {e}")
        self._conn.executescript(_SCHEMA)
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(facts)").fetchall()}
        # Inline re-implementation of hermes_cli.sqlite_util.add_column_if_missing: backfills columns added
        # after an older DB was created, so upgraded stores keep working.
        legacy_defaults = {
            "status": "TEXT DEFAULT 'active'",
            "agent_id": "TEXT DEFAULT ''",
            "device_id": "TEXT DEFAULT ''",
            "session_id": "TEXT DEFAULT ''",
            "hrr_vector": "BLOB",
        }
        for column, ddl in legacy_defaults.items():
            if column not in columns:
                self._conn.execute(f"ALTER TABLE facts ADD COLUMN {column} {ddl}")
        self._conn.executescript(_SCHEMA_INDEXES)
        # Create memory_times table if absent
        has_memory_times = any(row[1] for row in self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_times'"
        ).fetchall())
        if not has_memory_times:
            self._conn.executescript(_CREATE_MEMORY_TIMES)
        self._conn.commit()

    def _one(self, sql: str, params=()):
        return self._conn.execute(sql, params).fetchone()

    def _write(self, sql: str, params=()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def add_fact(self, content: str, category: str = "general", tags: str = "", trust_score: float | None = None,
                 status: str = "active", agent_id: str = "", device_id: str = "", session_id: str = "") -> int:
        """Insert a fact and return its fact_id; on duplicate content (UNIQUE) return the existing fact_id untouched.
        Links extracted entities and rebuilds the category bank. The source triple (agent/device/session) is
        recorded on first insert only — a duplicate write is idempotent and never rewrites provenance."""
        with self._lock:
            content = content.strip()
            if not content:
                raise ValueError("content must not be empty")
            trust = self.default_trust if trust_score is None else _clamp_trust(float(trust_score))
            try:
                fact_id: int = self._write(
                    "INSERT INTO facts (content, category, tags, trust_score, status, agent_id, device_id, session_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (content, category, tags, trust, status, agent_id, device_id, session_id)).lastrowid  # type: ignore[assignment]
            except sqlite3.IntegrityError:
                return int(self._one("SELECT fact_id FROM facts WHERE content = ?", (content,))["fact_id"])
            self._link_entities(fact_id, content)
            self._compute_hrr_vector(fact_id, content)
            self._rebuild_bank(category)
            return fact_id

    def update_fact(self, fact_id: int, content: str | None = None, trust_delta: float | None = None,
                    tags: str | None = None, category: str | None = None,
                    status: str | None = None, agent_id: str | None = None,
                    device_id: str | None = None, session_id: str | None = None) -> bool:
        """Partially update a fact (trust clamped to [0, 1]). Returns True if the row existed."""
        with self._lock:
            row = self._one("SELECT fact_id, trust_score FROM facts WHERE fact_id = ?", (fact_id,))
            if row is None:
                return False
            changes = {col: val for col, val in {
                "content": content.strip() if content is not None else None, "tags": tags, "category": category,
                "trust_score": _clamp_trust(row["trust_score"] + trust_delta) if trust_delta is not None else None,
                "status": status, "agent_id": agent_id, "device_id": device_id, "session_id": session_id,
            }.items() if val is not None}
            assignments = ", ".join(["updated_at = CURRENT_TIMESTAMP"] + [f"{col} = ?" for col in changes])
            self._write(f"UPDATE facts SET {assignments} WHERE fact_id = ?", [*changes.values(), fact_id])
            if content is not None:  # re-extract entities and recompute the HRR vector
                self._write("DELETE FROM fact_entities WHERE fact_id = ?", (fact_id,))
                self._link_entities(fact_id, content)
                self._compute_hrr_vector(fact_id, content)
            self._rebuild_bank(category or self._one("SELECT category FROM facts WHERE fact_id = ?", (fact_id,))["category"])
            return True

    def remove_fact(self, fact_id: int) -> bool:
        """Delete a fact and its entity links. Returns True if the row existed."""
        with self._lock:
            row = self._one("SELECT fact_id, category FROM facts WHERE fact_id = ?", (fact_id,))
            if row is None:
                return False
            self._conn.execute("DELETE FROM fact_entities WHERE fact_id = ?", (fact_id,))
            self._write("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
            self._rebuild_bank(row["category"])
            return True

    def list_facts(self, category: str | None = None, min_trust: float = 0.0, limit: int = 50,
                   include_rejected: bool = False) -> list[dict]:
        """Browse facts ordered by trust_score descending, optionally filtered by category / min trust.
        Rejected facts are excluded unless include_rejected is set (hermes had no status column at all)."""
        with self._lock:
            status_clause = "" if include_rejected else "AND status = 'active' "
            category_clause = "AND category = ? " if category is not None else ""
            params = [min_trust] + ([category] if category is not None else []) + [limit]
            sql = (f"SELECT {_FACT_PUBLIC_COLUMNS} FROM facts WHERE trust_score >= ? "
                   f"{category_clause}{status_clause}ORDER BY trust_score DESC LIMIT ?")
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]
    def record_feedback(self, fact_id: int, helpful: bool) -> dict:
        """Adjust trust asymmetrically: helpful -> +0.05 and helpful_count += 1; unhelpful -> -0.10.
        Returns {fact_id, old_trust, new_trust, helpful_count}. Raises KeyError if fact_id is unknown."""
        with self._lock:
            row = self._one("SELECT fact_id, trust_score, helpful_count FROM facts WHERE fact_id = ?", (fact_id,))
            if row is None:
                raise KeyError(f"fact_id {fact_id} not found")
            old_trust: float = row["trust_score"]
            new_trust = _clamp_trust(old_trust + (_HELPFUL_DELTA if helpful else _UNHELPFUL_DELTA))
            increment = 1 if helpful else 0
            self._write("UPDATE facts SET trust_score = ?, helpful_count = helpful_count + ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE fact_id = ?", (new_trust, increment, fact_id))
            return {"fact_id": fact_id, "old_trust": old_trust, "new_trust": new_trust, "helpful_count": row["helpful_count"] + increment}

    # ---- Admin-side operations (xiaozhi memory console) ---------------------------------------------

    def set_fact_status(self, fact_id: int, status: str) -> bool:
        """Set the fact status ('active' / 'rejected'). Returns True if the row existed."""
        with self._lock:
            row = self._one("SELECT fact_id FROM facts WHERE fact_id = ?", (fact_id,))
            if row is None:
                return False
            self._write("UPDATE facts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE fact_id = ?", (status, fact_id))
            return True

    def update_fact_trust(self, fact_id: int, trust_score: float) -> bool:
        """Set an absolute trust score (clamped to [0, 1]). Returns True if the row existed."""
        with self._lock:
            row = self._one("SELECT fact_id FROM facts WHERE fact_id = ?", (fact_id,))
            if row is None:
                return False
            self._write("UPDATE facts SET trust_score = ?, updated_at = CURRENT_TIMESTAMP WHERE fact_id = ?",
                        (_clamp_trust(float(trust_score)), fact_id))
            return True

    def set_fact_sources(self, fact_id: int, agent_id: str, device_id: str, session_id: str) -> bool:
        """Overwrite the source triple (used by the admin console to fix provenance). Returns True if the row existed."""
        with self._lock:
            row = self._one("SELECT fact_id FROM facts WHERE fact_id = ?", (fact_id,))
            if row is None:
                return False
            self._write("UPDATE facts SET agent_id = ?, device_id = ?, session_id = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE fact_id = ?", (agent_id, device_id, session_id, fact_id))
            return True

    def get_fact(self, fact_id: int) -> dict | None:
        with self._lock:
            row = self._one(f"SELECT {_FACT_PUBLIC_COLUMNS} FROM facts WHERE fact_id = ?", (fact_id,))
            return dict(row) if row is not None else None

    def get_entities(self, fact_id: int) -> list[str]:
        with self._lock:
            return [row["name"] for row in self._conn.execute(_ENTITY_NAMES_SQL, (fact_id,)).fetchall()]

    def count_facts(self, status: str | None = None) -> int:
        with self._lock:
            if status:
                return int(self._conn.execute("SELECT COUNT(*) FROM facts WHERE status = ?", (status,)).fetchone()[0])
            return int(self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])

    # ---- Time-reference operations ----------------------------------------------------------------

    def add_time_references(self, fact_id: int, refs: list[tuple[str, str | None]]) -> None:
        """Insert time references for a fact. No-op if fact_id does not exist."""
        with self._lock:
            existing = self._one("SELECT fact_id FROM facts WHERE fact_id = ?", (fact_id,))
            if existing is None:
                return
            self._write(
                "INSERT OR IGNORE INTO memory_times (memory_id, time_reference, actual_date) VALUES (?, ?, ?)",
                [(fact_id, ref, date) for ref, date in refs],
            )

    def remove_time_references(self, fact_id: int) -> int:
        """Delete all time references for a fact. Returns count deleted."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM memory_times WHERE memory_id = ?", (fact_id,))
            self._conn.commit()
            return cur.rowcount

    def get_time_references(self, fact_id: int) -> list[dict]:
        """Return time references for a fact as list of dicts."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT time_reference, actual_date FROM memory_times WHERE memory_id = ? ORDER BY rowid",
                (fact_id,),
            ).fetchall()
            return [{"time_reference": r["time_reference"], "actual_date": r["actual_date"]} for r in rows]

    def get_timeline(self, from_time: str | None = None, to_time: str | None = None,
                     limit: int = 50, offset: int = 0) -> dict:
        """Return facts ordered by created_at with their time references (for timeline view)."""
        with self._lock:
            conditions, params = [], []
            if from_time:
                conditions.append("f.created_at >= ?")
                params.append(from_time)
            if to_time:
                conditions.append("f.created_at <= ?")
                params.append(to_time)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            count_sql = f"SELECT COUNT(*) FROM facts f {where}"
            total = int(self._conn.execute(count_sql, params).fetchone()[0])
            page = max(1, int(offset // limit if limit else 1))
            limit = min(100, max(1, int(limit)))
            offset = max(0, int(offset))
            sql = (f"SELECT {', '.join('f.' + col for col in _FACT_PUBLIC_COLUMNS.split(', '))} "
                   f"FROM facts f {where} ORDER BY f.created_at DESC LIMIT ? OFFSET ?")
            rows = self._conn.execute(sql, [*params, limit, offset]).fetchall()
            items = []
            for row in rows:
                d = self._fact_dict(row)
                d["time_references"] = [
                    {"time_reference": r["time_reference"], "actual_date": r["actual_date"]}
                    for r in self._conn.execute(
                        "SELECT time_reference, actual_date FROM memory_times WHERE memory_id = ?",
                        (d["fact_id"],),
                    ).fetchall()
                ]
                items.append(d)
            return {"total": total, "items": items, "limit": limit, "offset": offset}

    def get_chart_data(self, period: str = "daily", from_date: str | None = None,
                       to_date: str | None = None) -> dict:
        """Return chart data for memory statistics.

        Args:
            period: 'daily', 'weekly', or 'monthly'
            from_date: start date in YYYY-MM-DD format (optional, defaults to 30 days ago)
            to_date: end date in YYYY-MM-DD format (optional, defaults to today)

        Returns:
            {"labels": [...], "counts": [...], "period": str, "from_date": str, "to_date": str}
        """
        from datetime import datetime, timedelta

        with self._lock:
            now = datetime.now()
            if to_date:
                end_dt = datetime.fromisoformat(to_date)
            else:
                end_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if from_date:
                start_dt = datetime.fromisoformat(from_date)
            elif period == "monthly":
                start_dt = (end_dt - timedelta(days=365)).replace(day=1)
            elif period == "weekly":
                start_dt = (end_dt - timedelta(weeks=12)).replace(weekday=end_dt.weekday())
            else:  # daily
                start_dt = (end_dt - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)

            # Build date range labels
            if period == "daily":
                deltas = [(end_dt - timedelta(days=i)).date() for i in range(30, -1, -1)]
                date_format = "%Y-%m-%d"
            elif period == "weekly":
                deltas = []
                current = start_dt.date()
                while current <= end_dt.date():
                    deltas.append(current)
                    current += timedelta(weeks=1)
                date_format = "%Y-W%W"
            else:  # monthly
                deltas = []
                current = start_dt.replace(day=1)
                while current <= end_dt:
                    deltas.append(current.date())
                    if current.month == 12:
                        current = current.replace(year=current.year + 1, month=1)
                    else:
                        current = current.replace(month=current.month + 1)
                date_format = "%Y-%m"

            # Query counts per period
            if period == "daily":
                sql = """
                    SELECT DATE(created_at) as date_str, COUNT(*) as cnt
                    FROM facts
                    WHERE created_at >= ? AND created_at <= ?
                    GROUP BY DATE(created_at)
                    ORDER BY date_str
                """
                params = [start_dt.isoformat(), end_dt.isoformat()]
            elif period == "weekly":
                sql = """
                    SELECT strftime('%Y-W%W', created_at) as date_str, COUNT(*) as cnt
                    FROM facts
                    WHERE created_at >= ? AND created_at <= ?
                    GROUP BY strftime('%Y-W%W', created_at)
                    ORDER BY date_str
                """
                params = [start_dt.isoformat(), end_dt.isoformat()]
            else:  # monthly
                sql = """
                    SELECT strftime('%Y-%m', created_at) as date_str, COUNT(*) as cnt
                    FROM facts
                    WHERE created_at >= ? AND created_at <= ?
                    GROUP BY strftime('%Y-%m', created_at)
                    ORDER BY date_str
                """
                params = [start_dt.isoformat(), end_dt.isoformat()]

            rows = self._conn.execute(sql, params).fetchall()
            count_map = {row["date_str"]: row["cnt"] for row in rows}

            # Build labels and counts arrays
            if period == "daily":
                labels = [d.strftime(date_format) for d in deltas]
            elif period == "weekly":
                labels = [d.strftime(date_format) for d in deltas]
            else:
                labels = [d.strftime(date_format) for d in deltas]

            counts = [count_map.get(d.strftime(date_format), 0) for d in deltas]

            return {
                "labels": labels,
                "counts": counts,
                "period": period,
                "from_date": start_dt.strftime("%Y-%m-%d"),
                "to_date": end_dt.strftime("%Y-%m-%d"),
                "total": sum(counts),
            }

    def _fact_dict(self, row: sqlite3.Row) -> dict:
        fact = dict(row)
        fact.pop("hrr_vector", None)
        return fact

    def search_facts(self, keyword: str = "", category: str | None = None, status: str | None = None,
                     trust_min: float | None = None, trust_max: float | None = None,
                     start: str | None = None, end: str | None = None,
                     page: int = 1, size: int = 20, sort_by: str = "created", order: str = "desc") -> dict:
        """Admin console query (aligns with design §3.1 /memory/{agent_id}/facts list parameters).
        keyword goes through the FTS5 index; all other filters are applied on the facts table directly.
        status=None (default) lists active facts only; status='rejected'/'active' filters explicitly —
        the console needs to show rejected facts for restore. Returns {total, items, matched_terms}.
        sort_by in {'created', 'trust'}."""
        with self._lock:
            conditions, params = [], []
            if keyword and keyword.strip():
                # Chinese recall fix (py-review finding): FTS5 unicode61 treats a whole CJK
                # run as ONE token, so a phrase MATCH on Chinese keywords returns nothing.
                # Mirror the retrieval layer strategy: phrase MATCH OR LIKE substring over
                # the whole keyword and its CJK-run bigrams (喜欢什么歌 → 喜欢/欢什/什么/么歌;
                # 喜欢 ⊂ 我喜欢听粤语歌). Embedded quotes are doubled so a raw " cannot
                # break out of the phrase (FTS5 syntax error / injection).
                from .holographic import cjk_runs
                trimmed = keyword.strip()
                token = trimmed.replace('"', '""')
                # Round-robin needles (mirrors retrieval._merge_like_candidates): whole
                # query first, then each CJK run, then per-position interleaved bigrams
                # of all runs, so a multi-run keyword keeps early seats for every run
                # (you also remember me?/what do I like -> the "like what" run survives).
                runs = cjk_runs(trimmed)
                like_needles = [trimmed, *runs]
                for pos in range(max((len(r) - 1 for r in runs), default=0)):
                    for run in runs:
                        if pos + 1 < len(run):
                            like_needles.append(run[pos] + run[pos + 1])
                like_needles = like_needles[:8]  # bound OR-terms (aligned with retrieval)
                like_clause = " OR ".join(["f.content LIKE ? ESCAPE '\\'"] * len(like_needles))
                conditions.append(
                    "(f.fact_id IN (SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?)"
                    f" OR {like_clause})")
                params.append(f'"{token}"')
                params.extend(f"%{_like_escape(needle)}%" for needle in like_needles)
            if category:
                conditions.append("f.category = ?")
                params.append(category)
            if status:
                conditions.append("f.status = ?")
                params.append(status)
            else:
                conditions.append("f.status = 'active'")
            if trust_min is not None:
                conditions.append("f.trust_score >= ?")
                params.append(float(trust_min))
            if trust_max is not None:
                conditions.append("f.trust_score <= ?")
                params.append(float(trust_max))
            if start:
                conditions.append("f.created_at >= ?")
                params.append(start)
            if end:
                conditions.append("f.created_at <= ?")
                params.append(end)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            order_by = "ORDER BY f.created_at DESC" if sort_by == "created" else "ORDER BY f.trust_score DESC"
            if order == "asc":
                order_by = order_by.replace("DESC", "ASC")
            count_sql = f"SELECT COUNT(*) FROM facts f {where}"
            total = int(self._conn.execute(count_sql, params).fetchone()[0])
            page = max(1, int(page))
            size = min(100, max(1, int(size)))
            offset = (page - 1) * size
            sql = (f"SELECT {', '.join('f.' + col for col in _FACT_PUBLIC_COLUMNS.split(', '))} FROM facts f {where} "
                   f"{order_by} LIMIT ? OFFSET ?")
            items = [self._fact_dict(row) for row in self._conn.execute(sql, [*params, size, offset]).fetchall()]
            return {"total": total, "items": items, "page": page, "size": size,
                    "matched_terms": [keyword.strip()] if keyword else []}

    def _extract_entities(self, text: str) -> list[str]:
        """Regex entity candidates (see the pattern table), deduplicated case-insensitively in first-seen order."""
        raw = [m.group(1) for pattern in _RE_SINGLE_ENTITY for m in pattern.finditer(text)]
        for m in _RE_AKA.finditer(text):
            raw += [m.group(1), m.group(2)]
        uniq: dict[str, str] = {}  # lower-cased key -> first-seen spelling, insertion-ordered
        for name in filter(None, (n.strip() for n in raw)):
            uniq.setdefault(name.lower(), name)
        return list(uniq.values())

    def _link_entities(self, fact_id: int, content: str) -> None:
        """Extract entities from content, resolve/create them, and link each to the fact."""
        for name in self._extract_entities(content):
            self._write("INSERT OR IGNORE INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
                        (fact_id, self._resolve_entity(name)))

    def _resolve_entity(self, name: str) -> int:
        """Return the entity_id for a case-insensitive name or alias match, creating the entity if absent."""
        for sql in _ENTITY_LOOKUPS:
            row = self._one(sql, (name,))
            if row is not None:
                return int(row["entity_id"])
        return int(self._write("INSERT INTO entities (name) VALUES (?)", (name,)).lastrowid)  # type: ignore[arg-type]

    def _compute_hrr_vector(self, fact_id: int, content: str) -> None:
        """Compute and store the HRR vector for a fact (linked entities as roles). No-op without numpy."""
        if not self._hrr_available:
            return
        entities = [row["name"] for row in self._conn.execute(_ENTITY_NAMES_SQL, (fact_id,)).fetchall()]
        blob = hrr.phases_to_bytes(hrr.encode_fact(content, entities, self.hrr_dim))
        self._write("UPDATE facts SET hrr_vector = ? WHERE fact_id = ?", (blob, fact_id))

    def _rebuild_bank(self, category: str) -> None:
        """Full rebuild of a category's memory bank from all its fact vectors."""
        if not self._hrr_available:
            return
        bank_name = f"cat:{category}"
        rows = self._conn.execute("SELECT hrr_vector FROM facts WHERE category = ? AND hrr_vector IS NOT NULL", (category,)).fetchall()
        if not rows:
            self._write("DELETE FROM memory_banks WHERE bank_name = ?", (bank_name,))
            return
        bank_vector = hrr.bundle(*[hrr.bytes_to_phases(row["hrr_vector"], dim=self.hrr_dim) for row in rows])
        hrr.snr_estimate(self.hrr_dim, len(rows))  # warns when near capacity
        self._write("INSERT INTO memory_banks (bank_name, vector, dim, fact_count, updated_at) "
                    "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(bank_name) DO UPDATE SET "
                    "vector = excluded.vector, dim = excluded.dim, fact_count = excluded.fact_count, "
                    "updated_at = excluded.updated_at", (bank_name, hrr.phases_to_bytes(bank_vector), self.hrr_dim, len(rows)))

    @classmethod
    def release_all_under(cls, directory: "str | Path") -> int:
        """Force-close every shared connection whose database lives under ``directory``; returns the count.
        close() is refcount-driven, so a live holder (e.g. an agent's provider) keeps a profile's SQLite handle
        open, which on Windows makes rmtree of the profile fail. The directory is going away, so later use by a
        stale holder is expected to fail.
        """
        root = os.path.normcase(str(Path(directory).expanduser().resolve())) + os.sep
        with cls._shared_guard:
            doomed = [cls._shared.pop(key) for key in list(cls._shared) if os.path.normcase(key).startswith(root)]
            for entry in doomed:
                try:
                    with entry["lock"]:
                        entry["conn"].close()
                except Exception:
                    pass  # an already-closed/broken connection must not abort releasing siblings
        return len(doomed)

    def close(self) -> None:
        """Release this instance's reference; the connection closes with the last holder. Idempotent."""
        with MemoryStore._shared_guard:
            entry = getattr(self, "_entry", None)
            if entry is None:
                return
            entry["refs"] -= 1
            if entry["refs"] <= 0:
                try:
                    entry["conn"].close()
                finally:
                    # Pop only OUR entry: after release_all_under() a same-path store may have
                    # registered a FRESH entry under this key; a stale late close() must not evict it.
                    if MemoryStore._shared.get(self._key) is entry:
                        MemoryStore._shared.pop(self._key, None)
            self._entry = None

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
