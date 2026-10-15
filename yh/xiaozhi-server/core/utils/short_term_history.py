"""短期记忆存储：按 agent_id 持久化最近的真实对话消息（SQLite）。

设计（短期记忆功能，2026-10）：
- 数据源：设备对话链每轮结束时（connection.py chat() 尾部）把本轮新增的
  user/assistant 消息追加到本地 SQLite（data/memory/short_term_history.db，
  与 mem_holographic 同目录约定）；跳过 few-shot（is_temporary）、tool_calls、
  tool 消息，只保留真实对话。
- 读取：会话初始化时按 agent_id 预取最近 N 条（short_term_turns，默认 10），
  之后每轮与「本会话已产生的真实消息」合并、截尾到 N 条，以
  <short_term_memory> 标记块注入 system prompt（见 dialogue.py）。
- 边界：记录不足 N 条时全量注入；单条超长截断（MAX_CONTENT_LEN=500 字符）；
  任一读写失败静默降级（不注入/不持久化），绝不影响对话主流程。
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

from config.config_loader import get_project_dir
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

# 单条消息截断长度（字符）
MAX_CONTENT_LEN = 500

# 每 agent 保留的记录条数上限（防止库无限增长；N 条注入 + 余量）
RETENTION_PER_AGENT = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS short_term_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sth_agent ON short_term_history(agent_id, id);
"""

# 进程级锁：chat 线程尾部落盘与连接关闭落盘可能并发
_lock = threading.Lock()


def _get_db_path(db_dir=None) -> Path:
    root = Path(str(db_dir)) if db_dir else Path("data/memory")
    if not root.is_absolute():
        root = Path(get_project_dir()) / root
    return root / "short_term_history.db"


def clean_content(content) -> str:
    """提取纯文本：剥离 ASR JSON 包裹（{"content":...,"speaker":...}），非法输入返回空串。"""
    if not content or not isinstance(content, str):
        return ""
    text = content.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("content"):
                return str(data["content"]).strip()
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return text


def format_line(role: str, content) -> str:
    """格式化为 [用户]/[助手] 单行（含 500 字符截断）。"""
    text = clean_content(content)
    if not text:
        return ""
    who = "用户" if role == "user" else "助手"
    return f"[{who}] {text[:MAX_CONTENT_LEN]}"


# 系统注入的伪 user 消息前缀（如工具调用深度超限提醒），不属于真实对话
SYSTEM_NOISE_PREFIX = "[系统提示]"


def is_real_chat_message(m) -> bool:
    """判断 Message 是否为真实对话消息：user/assistant、非 few-shot、非工具调用、
    内容非空、非系统注入噪声。供落盘与会话合并两侧共用同一过滤口径。"""
    role = getattr(m, "role", None)
    if role not in ("user", "assistant"):
        return False
    if getattr(m, "is_temporary", False):
        return False
    if getattr(m, "tool_calls", None):
        return False
    text = clean_content(getattr(m, "content", None))
    return bool(text) and not text.startswith(SYSTEM_NOISE_PREFIX)


def persist_session_turns(agent_id, msgs, db_dir=None):
    """把本轮新增的真实 user/assistant 消息追加入库（幂等由调用方增量下标保证）。

    msgs 为 Message 对象列表；few-shot（is_temporary）、tool_calls、tool 消息、
    系统噪声自动跳过。任何失败仅记日志，不影响对话。
    """
    if not agent_id or not msgs:
        return
    rows = []
    now = time.time()
    for m in msgs:
        role = getattr(m, "role", None)
        if not is_real_chat_message(m):
            continue
        line = format_line(role, getattr(m, "content", None))
        if line:
            # 存原始 role/content，格式化在读取侧做，保持库内数据中性
            rows.append((agent_id, role, clean_content(getattr(m, "content", None))[:MAX_CONTENT_LEN], now))
    if not rows:
        return
    try:
        with _lock:
            db_path = _get_db_path(db_dir)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), timeout=5)
            try:
                conn.executescript(_SCHEMA)
                conn.executemany(
                    "INSERT INTO short_term_history(agent_id, role, content, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                )
                conn.execute(
                    "DELETE FROM short_term_history WHERE agent_id = ? AND id NOT IN ("
                    "  SELECT id FROM short_term_history WHERE agent_id = ? "
                    "  ORDER BY id DESC LIMIT ?)",
                    (agent_id, agent_id, RETENTION_PER_AGENT),
                )
                conn.commit()
            finally:
                conn.close()
        logger.bind(tag=TAG).debug(f"短期记忆已写入 {len(rows)} 条 (agent={agent_id})")
    except Exception as e:
        logger.bind(tag=TAG).warning(f"短期记忆写入失败（不影响对话）: {e}")


def get_recent_lines(agent_id, limit=10, db_dir=None):
    """读取某 agent 最近 limit 条真实消息（时间正序），返回格式化行列表。

    不足 limit 条时全量返回；无记录/出错返回空列表（上层不注入该块）。
    """
    if not agent_id or not limit or int(limit) <= 0:
        return []
    try:
        with _lock:
            conn = sqlite3.connect(str(_get_db_path(db_dir)), timeout=5)
            try:
                conn.executescript(_SCHEMA)
                cur = conn.execute(
                    "SELECT role, content FROM ("
                    "  SELECT id, role, content FROM short_term_history "
                    "  WHERE agent_id = ? ORDER BY id DESC LIMIT ?"
                    ") ORDER BY id ASC",
                    (agent_id, int(limit)),
                )
                rows = cur.fetchall()
            finally:
                conn.close()
        lines = []
        for role, content in rows:
            line = format_line(role, content)
            if line:
                lines.append(line)
        return lines
    except Exception as e:
        logger.bind(tag=TAG).warning(f"短期记忆读取失败（本次不注入）: {e}")
        return []
