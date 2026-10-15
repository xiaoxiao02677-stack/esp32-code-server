"""Database manager for WeChatClawService.

Provides SQLite-based persistence for:
- User bindings (openid <-> device_id)
- Conversation history
- Scheduled tasks metadata
"""
import asyncio
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseManager:
    """SQLite database manager for WeChatClaw service."""

    def __init__(self, db_path: str = "wechat_claw.db"):
        self._db_path = db_path
        # Python 3.12 兼容：不使用 asyncio.local()

    # ── lifecycle ──────────────────────────────────────────────

    async def init(self) -> None:
        """Create tables if they do not exist."""
        self._sync_init()

    def _sync_init(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS user_bindings (
                    openid    TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    bound_at  REAL NOT NULL,
                    status    TEXT NOT NULL DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    timestamp  REAL NOT NULL,
                    metadata   TEXT DEFAULT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_user_ts
                    ON conversations(user_id, timestamp);

                CREATE TABLE IF NOT EXISTS schedules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    task_name  TEXT NOT NULL,
                    cron_expr  TEXT NOT NULL,
                    payload    TEXT NOT NULL DEFAULT '{}',
                    next_fire  REAL NOT NULL,
                    enabled    INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_run   REAL DEFAULT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_schedules_user_next
                    ON schedules(user_id, next_fire);
            """)
            conn.commit()
        logger.info(f"Database initialised at {self._db_path}")

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> dict:
        return dict(row)

    @contextmanager
    def _conn(self):
        """Yield a connection with autocommit / row-factory."""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ── user bindings ──────────────────────────────────────────

    async def bind_user(
        self, openid: str, device_id: str
    ) -> Dict[str, Any]:
        now = time.time()
        self._bind_user_sync(openid, device_id, now)
        return {"openid": openid, "device_id": device_id, "bound_at": now}

    def _bind_user_sync(self, openid, device_id, now):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_bindings "
                "(openid, device_id, bound_at, status) VALUES (?, ?, ?, ?)",
                (openid, device_id, now, "active"),
            )
            conn.commit()

    async def unbind_user(self, openid: str) -> bool:
        result = self._unbind_user_sync(openid)
        return bool(result)

    def _unbind_user_sync(self, openid: str) -> Optional[int]:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE user_bindings SET status = ? WHERE openid = ?",
                ("inactive", openid),
            )
            conn.commit()
            return cur.rowcount

    async def get_user_device(self, openid: str) -> Optional[str]:
        return self._get_user_device_sync(openid)

    def _get_user_device_sync(self, openid: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT device_id FROM user_bindings "
                "WHERE openid = ? AND status = 'active'",
                (openid,),
            ).fetchone()
            return row["device_id"] if row else None

    async def get_user_openid(self, device_id: str) -> Optional[str]:
        return self._get_user_openid_sync(device_id)

    def _get_user_openid_sync(self, device_id: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT openid FROM user_bindings "
                "WHERE device_id = ? AND status = 'active'",
                (device_id,),
            ).fetchone()
            return row["openid"] if row else None

    async def list_active_users(self) -> List[Dict[str, Any]]:
        rows = self._list_active_users_sync()
        return [self._row_to_dict(r) for r in rows]

    def _list_active_users_sync(self) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT openid, device_id, bound_at FROM user_bindings "
                "WHERE status = 'active'"
            ).fetchall()

    # ── conversation history ───────────────────────────────────

    async def save_message(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> int:
        ts = time.time()
        mid = self._save_message_sync(
            user_id, role, content, ts,
            json.dumps(metadata) if metadata else None,
        )
        return mid

    def _save_message_sync(
        self,
        user_id: str,
        role: str,
        content: str,
        ts: float,
        meta_json: Optional[str],
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (user_id, role, content, timestamp, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, role, content, ts, meta_json),
            )
            conn.commit()
            return cur.lastrowid

    async def get_conversation_history(
        self,
        user_id: str,
        last_n: int = 20,
        after_ts: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        rows = self._get_conversation_history_sync(user_id, last_n, after_ts)
        return [self._row_to_dict(r) for r in rows]

    def _get_conversation_history_sync(
        self,
        user_id: str,
        last_n: int,
        after_ts: Optional[float],
    ) -> List[sqlite3.Row]:
        with self._conn() as conn:
            if after_ts is not None:
                rows = conn.execute(
                    "SELECT role, content, timestamp, metadata FROM conversations "
                    "WHERE user_id = ? AND timestamp > ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (user_id, after_ts, last_n),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT role, content, timestamp, metadata FROM conversations "
                    "WHERE user_id = ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (user_id, last_n),
                ).fetchall()
            # Return in chronological order
            return list(reversed(rows))

    async def clear_conversation(self, user_id: str) -> int:
        result = self._clear_conversation_sync(user_id)
        return result

    def _clear_conversation_sync(self, user_id: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE user_id = ?", (user_id,)
            )
            conn.commit()
            return cur.rowcount

    async def get_conversation_count(self, user_id: str) -> int:
        return self._get_conversation_count_sync(user_id)

    def _get_conversation_count_sync(self, user_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM conversations WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    # ── scheduled tasks metadata ───────────────────────────────

    async def save_schedule(
        self,
        user_id: str,
        task_name: str,
        cron_expr: str,
        payload: Dict,
        next_fire: float,
    ) -> int:
        created_at = time.time()
        return self._save_schedule_sync(
            user_id, task_name, cron_expr,
            json.dumps(payload), next_fire, created_at,
        )

    def _save_schedule_sync(
        self,
        user_id: str,
        task_name: str,
        cron_expr: str,
        payload_json: str,
        next_fire: float,
        created_at: float,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO schedules "
                "(user_id, task_name, cron_expr, payload, next_fire, enabled, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (user_id, task_name, cron_expr, payload_json, next_fire, created_at),
            )
            conn.commit()
            return cur.lastrowid

    async def list_schedules(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self._list_schedules_sync(user_id)
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            d["payload"] = json.loads(d.get("payload", "{}"))
            result.append(d)
        return result

    def _list_schedules_sync(self, user_id: str) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM schedules WHERE user_id = ? ORDER BY next_fire ASC",
                (user_id,),
            ).fetchall()

    async def delete_schedule(self, schedule_id: int, user_id: str) -> bool:
        result = self._delete_schedule_sync(schedule_id, user_id)
        return bool(result)

    def _delete_schedule_sync(self, schedule_id: int, user_id: str) -> Optional[int]:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM schedules WHERE id = ? AND user_id = ?",
                (schedule_id, user_id),
            )
            conn.commit()
            return cur.rowcount

    async def update_next_fire(self, schedule_id: int, next_fire: float) -> bool:
        result = self._update_next_fire_sync(schedule_id, next_fire)
        return bool(result)

    def _update_next_fire_sync(self, schedule_id: int, next_fire: float) -> Optional[int]:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE schedules SET next_fire = ? WHERE id = ?",
                (next_fire, schedule_id),
            )
            conn.commit()
            return cur.rowcount

    async def mark_last_run(self, schedule_id: int) -> bool:
        now = time.time()
        result = self._mark_last_run_sync(schedule_id, now)
        return bool(result)

    def _mark_last_run_sync(self, schedule_id: int, now: float) -> Optional[int]:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE schedules SET last_run = ? WHERE id = ?",
                (now, schedule_id),
            )
            conn.commit()
            return cur.rowcount
