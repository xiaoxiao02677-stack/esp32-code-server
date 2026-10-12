"""mem_hybrid —— 组合记忆引擎：短期 LLM 总结 + Holographic 长期事实库。

设计（design §mem_hybrid，2026-10-08）：
- 短期层：复用 mem_local_short 的滚动总结（时空记忆编织者 prompt，可选独立总结 LLM）
- 长期层：复用 mem_holographic 的 SQLite 事实库（正则自动抽取 + HRR 检索）
- 沉淀通道（新增）：会话结束时，用 LLM 从「滚动总结 + 本轮对话」中提取值得长期
  记住的 facts（类别 preference/habit/profile/event），写入 Holographic。
  LLM 不可用/未配置时静默跳过（退化为双层无沉淀，正则抽取仍在）。

配置（config_json）：
  {"type": "mem_hybrid", "llm": "LLM_DeepSeek", "db_dir": "data/memory/",
   "auto_extract": true, "default_trust": 0.5, "min_trust_threshold": 0.3,
   "temporal_decay_half_life": 0, "distill_facts": true, "distill_max_facts": 5}
llm 字段由 Java ConfigServiceImpl 解析并注入附加 LLM 配置（同 mem_local_short 模式）。
"""
import json
import time

from config.logger import setup_logging
from core.providers.memory.base import MemoryProviderBase

TAG = __name__
logger = setup_logging()

# 事实沉淀 prompt：从总结+对话提取长期 facts（JSON 数组输出，控制在 distill_max_facts 条）
DISTILL_PROMPT = """# 长期记忆管理员

## 任务
从「用户档案总结」与「本轮对话记录」中提取值得**长期记住**的用户事实。
只提取用户本人的稳定事实，不要提取 AI 的回复内容、临时性闲聊、一次性问题。

## 输出类别
- preference：用户偏好（喜欢/讨厌/想要/不吃/爱听…）
- habit：习惯（总是/从不/每天/经常…）
- profile：画像（是/叫/住在/从事/性格…）
- event：重要事件（今天/昨天/刚发生且影响未来的…）

## 输出格式（严格遵守，可解析 JSON，不加任何解释）
{"facts": [{"content": "用户喜欢听粤语歌", "category": "preference"}, ...]}
没有值得提取的内容时输出 {"facts": []}
"""


def _parse_distill_json(text):
    """解析 LLM 输出的 facts JSON（容错：```json 包裹/前后噪声）。"""
    if not text:
        return []
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, list):
        return []
    out = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        content = str(f.get("content") or "").strip()
        category = str(f.get("category") or "general").strip()
        if content and 3 <= len(content) <= 400 and category in (
                "preference", "habit", "profile", "event", "general"):
            out.append({"content": content, "category": category})
    return out


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory=None):
        super().__init__(config)
        self.config = config or {}
        self.summary_memory = summary_memory or ""
        self.auto_extract = bool(self.config.get("auto_extract", True))
        self.distill_facts = bool(self.config.get("distill_facts", True))
        self.distill_max_facts = int(self.config.get("distill_max_facts", 5))
        self.db_dir = self.config.get("db_dir", "data/memory/")
        self.default_trust = float(self.config.get("default_trust", 0.5))
        self.min_trust_threshold = float(self.config.get("min_trust_threshold", 0.3))
        self.temporal_decay_half_life = int(self.config.get("temporal_decay_half_life", 0))

        # 角色命名空间（init_memory 时回填）
        self.role_id = None
        self.agent_id = ""
        self.device_id = ""
        self.session_id = ""

        # 子引擎延迟创建（init_memory 后才有 agent_id）
        self._store = None
        self._retriever = None
        self.llm = None

    # ---------- 基类协议 ----------
    def init_memory(self, role_id, llm, agent_id=None, device_id=None,
                    session_id=None, **kwargs):
        super().init_memory(role_id, llm, **kwargs)
        self.role_id = role_id
        self.llm = llm
        self.agent_id = agent_id or role_id
        self.device_id = device_id or ""
        self.session_id = session_id or ""

        # 长期层：Holographic store（与 mem_holographic 同一实现，同库兼容）
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        from core.providers.memory.mem_holographic.retrieval import FactRetriever

        self._store = get_store(
            self.agent_id, db_dir=self.db_dir,
            default_trust=self.default_trust,
        )
        self._retriever = FactRetriever(
            store=self._store,
            temporal_decay_half_life=self.temporal_decay_half_life,
        )

    def set_llm(self, llm):
        """总结专用 LLM（connection.py 在配置 llm 字段时注入；否则用主 LLM）。"""
        self.llm = llm

    # ---------- 写入 ----------
    async def save_memory(self, msgs, session_id=None):
        if session_id and self.session_id is None:
            self.session_id = session_id

        # ① 长期层：正则自动抽取（零成本，与 mem_holographic 一致）
        try:
            self._auto_extract_facts(msgs)
        except Exception as e:
            logger.bind(tag=TAG).error(f"hybrid 正则抽取失败: {e}")

        # ② 短期层 + ③ 沉淀：LLM 总结并把稳定事实沉淀进长期库
        try:
            await self._update_summary_and_distill(msgs)
        except Exception as e:
            logger.bind(tag=TAG).error(f"hybrid 总结/沉淀失败: {e}")
        return None

    # ---------- 纯函数工具（与 mem_holographic 同逻辑，避免跨类方法形态依赖） ----------
    @staticmethod
    def _extract_fact_text(content) -> str:
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
        if "？" in text or "?" in text:
            return True
        return any(q in text for q in ("吗", "呢", "什么", "怎么", "为什么", "谁", "几", "多少", "哪"))

    @staticmethod
    def _strip_fillers(text: str) -> str:
        return text.strip("呃嗯啊哦唉呀哈嘛呢吧，。、 \t").strip()

    @staticmethod
    def _is_chitchat_event(text: str, match) -> bool:
        captured = (match.group(1) or "").strip()
        stripped = captured.rstrip("啊呀吧呢哈了哦嘛")
        if len(stripped) < 4:
            return True
        if any(p in stripped for p in ("啊", "呀", "吧")):
            return True
        import re as _re
        return any(pat.search(text) for pat in (
            _re.compile(r"天气"), _re.compile(r"吃饭"), _re.compile(r"睡"),
        ))

    def _auto_extract_facts(self, msgs):
        """复用 mem_holographic 的正则规则（同一套 _EXTRACT_RULES）。"""
        from core.providers.memory.mem_holographic.mem_holographic import _EXTRACT_RULES
        extracted = 0
        for msg in msgs:
            role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
            if role != "user":
                continue
            text = self._extract_fact_text(content)
            text = self._strip_fillers(text)
            if len(text) < 4 or self._is_question_text(text):
                continue
            for pattern, category in _EXTRACT_RULES:
                match = pattern.search(text)
                if not match:
                    continue
                if category == "event" and self._is_chitchat_event(text, match):
                    continue
                if len(text) < 7 and category not in ("preference", "profile"):
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
                break
        if extracted:
            logger.bind(tag=TAG).info(f"hybrid 正则抽取 {extracted} 条事实")
        return extracted

    async def _update_summary_and_distill(self, msgs):
        """短期总结更新 + LLM 沉淀长期 facts。"""
        # 复用 mem_local_short 的总结 prompt 与 JSON 解析
        from core.providers.memory.mem_local_short.mem_local_short import (
            short_term_memory_prompt, extract_json_data,
        )
        if self.llm is None:
            logger.bind(tag=TAG).warning("hybrid 无 LLM，跳过总结/沉淀（仅正则抽取）")
            return

        if len(msgs) < 2:
            return

        msgStr = ""
        for msg in msgs:
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
            role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
            try:
                if content and isinstance(content, str) and content.strip().startswith("{"):
                    data = json.loads(content)
                    if "content" in data:
                        content = data["content"]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
            if role == "user":
                msgStr += f"User: {content}\n"
            elif role == "assistant":
                msgStr += f"Assistant: {content}\n"
        if self.summary_memory:
            msgStr += "历史记忆：\n" + self.summary_memory
        msgStr += "当前时间：" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        # ② 更新滚动总结（短期层）
        try:
            result = self.llm.response_no_stream(
                short_term_memory_prompt, msgStr, max_tokens=2000, temperature=0.2,
            )
            json_str = extract_json_data(result)
            json.loads(json_str)  # 校验
            self.summary_memory = json_str
            logger.bind(tag=TAG).info("hybrid 短期总结已更新")
        except Exception as e:
            logger.bind(tag=TAG).error(f"hybrid 短期总结失败: {e}")

        # ③ 沉淀：从总结+对话提取长期 facts
        if not self.distill_facts:
            return
        try:
            distill_input = (
                "用户档案总结：\n" + (self.summary_memory or "（无）")
                + "\n\n本轮对话记录：\n" + msgStr[:3000]
            )
            raw = self.llm.response_no_stream(
                DISTILL_PROMPT, distill_input, max_tokens=800, temperature=0.1,
            )
            facts = _parse_distill_json(raw)[: self.distill_max_facts]
            added = 0
            for f in facts:
                try:
                    self._store.add_fact(
                        f["content"], category=f["category"],
                        agent_id=self.agent_id or "",
                        device_id=self.device_id or "",
                        session_id=self.session_id or "",
                    )
                    added += 1
                except Exception:
                    pass
            if added:
                logger.bind(tag=TAG).info(f"hybrid LLM 沉淀 {added} 条长期事实")
        except Exception as e:
            logger.bind(tag=TAG).error(f"hybrid 沉淀失败: {e}")

    # ---------- 读取 ----------
    async def query_memory(self, query: str) -> str:
        """检索长期事实库（HRR+FTS5，阈值过滤），短期总结由 Java summaryMemory 管道注入。"""
        try:
            if not self._retriever or not query:
                return ""
            results = self._retriever.search(
                query, min_trust=self.min_trust_threshold, limit=5
            )
            if not results:
                return ""
            lines = [f"- [{r.get('trust_score', 0.5):.1f}] {r.get('content', '')}"
                     for r in results]
            return "\n".join(lines)
        except Exception as e:
            logger.bind(tag=TAG).error(f"hybrid 查询记忆失败: {e}")
            return ""

    def get_status(self) -> dict:
        return {
            "engine": "mem_hybrid",
            "available": True,
            "reason": "短期LLM总结 + Holographic长期事实库 + LLM沉淀",
            "distill": self.distill_facts,
        }


def create_instance(config, summary_memory=None):
    return MemoryProvider(config, summary_memory)
