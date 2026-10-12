"""xiaozhi-server provider boundary for the vendored hermes holographic memory engine.

Implements ``MemoryProviderBase`` the same way ``mem0ai`` / ``mem_local_short`` do:

- ``MemoryProvider`` is constructed per device connection with the engine config
  (``core/utils/memory.py:create_instance`` looks for ``MemoryProvider`` here).
- ``init_memory(role_id=agent_id, llm, agent_id=..., device_id=..., session_id=...)``
  binds one SQLite database per agent (``{db_dir}/{agent_id}.db``).
- ``save_memory`` auto-extracts facts from user messages when ``auto_extract`` is on
  (regex rules ported from the hermes plugin's ``_auto_extract_facts``, categories
  remapped to the PRD enum: preference/profile/habit/event/general).
- ``query_memory`` returns the Top-5 active facts with ``trust >= min_trust_threshold``.

A module-level ``weakref.WeakValueDictionary`` registry shares one ``MemoryStore``
instance per agent between the device link and the management HTTP handler.
"""

import json
import re
import threading
import weakref
from pathlib import Path

from ..base import MemoryProviderBase, logger
from .store import MemoryStore
from .retrieval import FactRetriever

TAG = __name__

# category enum per PRD §4.1
VALID_CATEGORIES = {"preference", "profile", "habit", "event", "general"}

# Auto-extraction rules (ported from hermes holographic __init__.py _EXTRACT_CATEGORIES,
# category names remapped to the PRD enum). Each rule is (pattern, category); the first
# matching rule wins, so more specific categories are listed first.
#
# D2 hardening (qa finding): the event rule needs chitchat guards or greetings like
# "今天天气真不错啊我们出去走走吧" get stored as facts. Guards, applied to the captured
# group: (a) trailing mood particles (吧呢啊呀嘛啦哦哟) stripped, remainder must be ≥4
# chars of substance; (b) a mood particle ANYWHERE inside the remainder marks
# exclamatory/invitational smalltalk (real event narration — 和朋友去公园散步聊天了 —
# carries aspect 了 but not 啊/呀/吧); (c) canonical weather/invitation smalltalk patterns.
_EVENT_TAIL_PARTICLES = "吧呢啊呀嘛啦哦哟哈了"
_EVENT_INNER_PARTICLES = tuple("吧呢啊呀嘛哟")
_EVENT_SMALLTALK_PATTERNS = (
    re.compile(r'天气.{0,3}(?:不错|很好|真好|真棒|不好|太差)'),
    re.compile(r'我们.{0,8}(?:出去|出去玩|出去走走|走走|走一走|散心)'),
)
_EXTRACT_RULES = (
    (re.compile(r'\bI\s+(?:prefer|like|love|use|want|need)\s+(.+)', re.IGNORECASE), "preference"),
    (re.compile(r'\bmy\s+(?:favorite|preferred|default)\s+\w+\s+is\s+(.+)', re.IGNORECASE), "preference"),
    (re.compile(r'\bI\s+(?:always|never|usually)\s+(.+)', re.IGNORECASE), "habit"),
    # 最喜欢 before 喜欢 so the adverb form wins the first-match race
    (re.compile(r'\b(?:我|俺)\s*(?:平时|一般|通常)?\s*(?:最)?喜欢\s*(.+)'), "preference"),
    (re.compile(r'\b(?:我|俺)\s*(?:爱|常用|想要|需要)\s*(.+)'), "preference"),
    (re.compile(r'\b(?:我|俺)\s*(?:总是|从不|通常|每天|经常)\s*(.+)'), "habit"),
    (re.compile(r'\b(?:我|俺)\s*(?:是|叫|住在|在|做|干|工作)\s*(.+)'), "profile"),
    (re.compile(r'\b(?:今天|昨天|上周)\s*(.+)'), "event"),
)

# Shared MemoryStore instances per agent, keyed by the resolved database path.
# WeakValueDictionary: when no provider/handler holds a reference the entry (and its
# SQLite connection) is released automatically. Guard covers dict mutation races.
_store_registry = weakref.WeakValueDictionary()
_registry_guard = threading.Lock()


def _normalize_category(category: str | None) -> str:
    category = (category or "").strip().lower() or "general"
    return category if category in VALID_CATEGORIES else "general"


def _safe_agent_id(agent_id) -> str:
    """Reject path traversal in agent ids used as database file names."""
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("agent_id must not be empty")
    if any(sep in agent_id for sep in ("/", "\\")) or agent_id in (".", ".."):
        raise ValueError(f"invalid agent_id: {agent_id!r}")
    return agent_id


def _resolve_db_dir(db_dir) -> Path:
    """Anchor relative db_dir values (default 'data/memory/') at the project root so the
    HTTP handler (any cwd) and the device link (project cwd) resolve the same directory.
    Lazy import: config_loader pulls in yaml and manage_api_client; the store itself must
    stay importable without any server-side dependencies."""
    from config.config_loader import get_project_dir
    db_dir = Path(str(db_dir)) if db_dir else Path("data/memory")
    return db_dir if db_dir.is_absolute() else Path(get_project_dir()) / db_dir


def get_store(agent_id: str, db_dir: str = "data/memory/", default_trust: float = 0.5,
              hrr_dim: int = 1024) -> MemoryStore:
    """Get the shared MemoryStore for an agent, creating it on first use.

    The device link and the management handler both call this, so both hit the same
    connection and the same RLock — writes are fully serialized across the two paths.
    """
    agent_id = _safe_agent_id(agent_id)
    db_path = _resolve_db_dir(db_dir) / f"{agent_id}.db"
    try:
        key = str(db_path.resolve())
    except OSError:
        key = str(db_path)
    with _registry_guard:
        store = _store_registry.get(key)
    if store is not None:
        return store
    with _registry_guard:
        store = _store_registry.get(key)  # double-checked under the guard
        if store is None:
            store = MemoryStore(db_path=str(db_path), default_trust=default_trust, hrr_dim=hrr_dim)
            _store_registry[key] = store
    return store


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory=None):
        super().__init__(config)
        self.db_dir = config.get("db_dir", "data/memory/")
        self.default_trust = float(config.get("default_trust", 0.5))
        self.min_trust_threshold = float(config.get("min_trust_threshold", 0.3))
        self.auto_extract = bool(config.get("auto_extract", True))
        self.temporal_decay_half_life = int(config.get("temporal_decay_half_life", 0))
        self.hrr_dim = int(config.get("hrr_dim", 1024))
        self.hrr_weight = float(config.get("hrr_weight", 0.3))
        self.agent_id = None
        self.device_id = None
        self.session_id = None
        self._store = None
        self._retriever = None

    def init_memory(self, role_id, llm, agent_id=None, device_id=None, session_id=None, **kwargs):
        """role_id is the memory namespace: the agent id (falls back to device id, see
        connection.py). The source triple is stored on every auto-extracted fact."""
        super().init_memory(role_id, llm, **kwargs)
        self.agent_id = agent_id or role_id
        self.device_id = device_id or ""
        self.session_id = session_id or ""
        self._store = get_store(self.agent_id, db_dir=self.db_dir, default_trust=self.default_trust,
                                hrr_dim=self.hrr_dim)
        self._retriever = FactRetriever(
            store=self._store,
            temporal_decay_half_life=self.temporal_decay_half_life,
            hrr_weight=self.hrr_weight,
            hrr_dim=self.hrr_dim,
        )

    def _extract_fact_text(self, content) -> str:
        """Unwrap the ASR JSON envelope ({"content": "..."} with emotion/language tags) if present."""
        if content is None:
            return ""
        try:
            if content.strip().startswith("{") and content.strip().endswith("}"):
                data = json.loads(content)
                if "content" in data:
                    content = data["content"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return content if isinstance(content, str) else ""

    @staticmethod
    def _is_question_text(text: str) -> bool:
        """Ten-probe quality fix: questions are not facts ("我叫什么名字?" / "你还记得我吗?").
        Treat interrogatives and question marks as non-facts."""
        if "？" in text or "?" in text:
            return True
        return any(q in text for q in ("吗", "呢", "什么", "怎么", "为什么", "谁", "几", "多少", "哪"))

    @staticmethod
    def _strip_fillers(text: str) -> str:
        """Ten-probe quality fix: strip leading spoken fillers ("呃", "嗯", "啊", "那个" ...)
        that hurt retrieval recall. Only trims edges; inner content is preserved."""
        return text.strip("呃嗯啊哦唉呀哈嘛呢吧，。、 ").strip()

    def _is_chitchat_event(self, text: str, match: "re.Match") -> bool:
        """D2 chitchat guard for the event rule (今天/昨天/上周 sentences):
        - canonical weather/invitation smalltalk patterns are never facts;
        - trailing mood particles stripped, remainder <4 chars is smalltalk;
        - a bare mood particle (啊/呀/吧...) inside the remainder marks exclamatory
          smalltalk — real narration (昨天和朋友去公园散步聊天了) uses none."""
        captured = (match.group(1) or "").strip()
        stripped = captured.rstrip(_EVENT_TAIL_PARTICLES)
        if len(stripped) < 4:
            return True
        if any(p in stripped for p in _EVENT_INNER_PARTICLES):
            return True
        return any(pat.search(text) for pat in _EVENT_SMALLTALK_PATTERNS)

    def _auto_extract_facts(self, msgs) -> int:
        """Regex-extract facts from user messages (ported from hermes _auto_extract_facts;
        the hermes compaction-summary special cases do not exist in xiaozhi and are dropped).

        Short-message gate: hermes used len<10, which drops the PRD's core A1 utterance
        "我喜欢听粤语歌" (7 chars) — lowered to 7 so canonical preference statements
        extract, while shorter fragments and pure smalltalk still do not."""
        if not self._store or not self.auto_extract:
            return 0
        extracted = 0
        for msg in msgs:
            role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
            if role != "user":
                continue
            text = self._extract_fact_text(content)
            text = self._strip_fillers(text)
            if len(text) < 4:
                continue  # too short to carry any fact
            if self._is_question_text(text):
                continue  # questions are not facts ("我叫什么名字?")
            for pattern, category in _EXTRACT_RULES:
                match = pattern.search(text)
                if not match:
                    continue
                if category == "event" and self._is_chitchat_event(text, match):
                    continue  # D2: greeting/smalltalk with a time word is not a fact
                if len(text) < 7 and category not in ("preference", "profile"):
                    continue  # very short: keep only explicit preference/profile statements
                if len(text) < 10 and category not in ("preference", "profile"):
                    # Below hermes' canonical 10-char gate, short habit/event fragments
                    # are usually ASR noise ("我每天跑步"); preference/profile statements
                    # ("我是广东人", "我喜欢听粤语歌") stay extractable.
                    continue
                try:
                    self._store.add_fact(
                        text[:400], category=category,
                        agent_id=self.agent_id or "",
                        device_id=self.device_id or "",
                        session_id=self.session_id or "",
                    )
                    extracted += 1
                except Exception:
                    pass
                break  # first matching rule wins
        if extracted:
            logger.bind(tag=TAG).info(f"Auto-extracted {extracted} facts from conversation")
        return extracted

    async def save_memory(self, msgs, session_id=None):
        if session_id and self.session_id is None:
            self.session_id = session_id
        try:
            self._auto_extract_facts(msgs)
        except Exception as e:
            logger.bind(tag=TAG).error(f"保存记忆失败: {str(e)}")
        return None

    async def query_memory(self, query: str) -> str:
        try:
            if not self._retriever or not query:
                return ""
            results = self._retriever.search(query, min_trust=self.min_trust_threshold, limit=5)
            if not results:
                return ""
            lines = [f"- [{r.get('trust_score', 0.5):.1f}] {r.get('content', '')}" for r in results]
            logger.bind(tag=TAG).debug(f"Query results: {lines}")
            return "\n".join(lines)
        except Exception as e:
            logger.bind(tag=TAG).error(f"查询记忆失败: {str(e)}")
            return ""

    def get_status(self) -> dict:
        """Engine availability for the console provider badge. SQLite is always available;
        numpy only upgrades similarity quality and is never a hard requirement."""
        from . import holographic as hrr
        return {
            "engine": "mem_holographic",
            "available": True,
            "reason": "本地 SQLite 引擎" if hrr._HAS_NUMPY else "本地 SQLite 引擎（NumPy 缺失，检索降级为 FTS5+Jaccard）",
            "numpy": hrr._HAS_NUMPY,
        }


def create_instance(config, summary_memory=None):
    """Entry point mirroring mem0ai.py, called by core/utils/memory.py:create_instance."""
    return MemoryProvider(config, summary_memory)
