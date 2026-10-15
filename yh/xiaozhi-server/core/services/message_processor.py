"""Message processor for WeChatClawService.

Handles:
- Converting raw WeChat messages into a normalised internal format
- Managing per-user multi-turn conversation context
- Calling the LLM backend and streaming / buffering responses
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# ── internal message types ───────────────────────────────────

@dataclass
class NormalisedMessage:
    """Internal normalised message representation."""

    role: str           # "user" | "assistant" | "system" | "tool"
    content: str
    message_id: str = ""
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NormalisedMessage":
        return cls(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            message_id=d.get("message_id", ""),
            timestamp=d.get("timestamp", 0.0),
            metadata=d.get("metadata", {}),
        )


# ── WeChat → NormalisedMessage ──────────────────────────────

WECHAT_MSG_TYPE_MAP = {
    "text":       "text",
    "image":      "image",
    "voice":      "voice",
    "video":      "video",
    "link":       "link",
    "location":   "location",
    "event":      "event",
    "event_subscribe": "event",
    "event_unsubscribe": "event",
    "event_scan": "event",
}


def parse_wechat_xml(xml_body: str) -> Optional[Dict[str, Any]]:
    """Parse incoming WeChat XML payload into a dict.

    Expected root element contains: ToUserName, FromUserName, MsgType,
    Content, MsgId,CreateTime, etc.
    """
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_body)
        result: Dict[str, Any] = {}
        for child in root:
            result[child.tag] = child.text or ""
        return result
    except Exception as exc:
        logger.warning(f"Failed to parse WeChat XML: {exc}")
        return None


def normalise_wechat_message(raw: Dict[str, Any]) -> NormalisedMessage:
    """Convert a raw WeChat message dict to NormalisedMessage.

    Only text messages are turned into conversational content;
    images/voice/etc. are stored with a placeholder so the LLM
    context remains well-formed.
    """
    msg_type = raw.get("MsgType", "text")
    content = raw.get("Content", "")
    message_id = raw.get("MsgId", "")

    # For non-text media, we store a hint so the LLM knows something was received
    if msg_type not in ("text", "event"):
        content = f"[{msg_type} message received — content not forwarded to LLM]"

    return NormalisedMessage(
        role="user",
        content=content,
        message_id=message_id,
        timestamp=datetime.now().timestamp(),
        metadata={"source": "wechat", "raw_type": msg_type, "raw": raw},
    )


# ── Conversation context manager ─────────────────────────────

MAX_CONTEXT_MESSAGES = 30   # keep last N turns to bound token usage


class ConversationContext:
    """Per-user multi-turn conversation state."""

    def __init__(self, user_id: str, system_prompt: str = ""):
        self.user_id = user_id
        self.system_prompt = system_prompt
        self.messages: List[NormalisedMessage] = []
        self.created_at = datetime.now().timestamp()
        self.last_interaction = self.created_at

    def add(self, msg: NormalisedMessage) -> None:
        self.messages.append(msg)
        self.last_interaction = msg.timestamp
        # Prune old messages to stay within token budget
        if len(self.messages) > MAX_CONTEXT_MESSAGES * 2:
            self.messages = self.messages[-MAX_CONTEXT_MESSAGES * 2:]

    def get_llm_dialogue(self) -> List[Dict[str, Any]]:
        """Return messages in the format expected by most LLM APIs."""
        dialogue: List[Dict[str, Any]] = []
        if self.system_prompt:
            dialogue.append({"role": "system", "content": self.system_prompt})
        for m in self.messages:
            dialogue.append(m.to_dict())
        return dialogue

    def clear(self) -> None:
        self.messages.clear()
        self.created_at = datetime.now().timestamp()


# ── LLM call wrapper ────────────────────────────────────────

LLMCallback = Callable[[str], asyncio.Future]  # streaming chunk callback


class LLMCaller:
    """Thin wrapper around the project's LLM provider.

    The actual provider is resolved lazily from config at call time so that
    the service can be started before the LLM module is fully initialised.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._llm_instance = None
        self._lock = asyncio.Lock()

    async def get_llm(self):
        """Lazily instantiate the LLM provider from config."""
        if self._llm_instance is not None:
            return self._llm_instance
        async with self._lock:
            if self._llm_instance is not None:
                return self._llm_instance
            self._llm_instance = await asyncio.get_event_loop().run_in_executor(
                None, self._build_llm_sync
            )
            return self._llm_instance

    def _build_llm_sync(self) -> Any:
        """Build LLM instance via the project's factory."""
        try:
            from core.utils.llm import create_instance  # pylint: disable=import-outside-toplevel
            llm_cfg = self.config.get("llm", {})
            llm_type = llm_cfg.get("provider", "deepseek")
            return create_instance(llm_type, self.config)
        except Exception as exc:
            logger.error(f"Failed to create LLM instance: {exc}")
            raise

    async def chat(
        self,
        dialogue: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        on_chunk: Optional[LLMCallback] = None,
    ) -> str:
        """Call LLM and return the assistant reply text.

        Parameters
        ----------
        dialogue : list[dict]
            Messages in OpenAI-like format, including optional system prompt.
        stream : bool
            If True, chunks are delivered via ``on_chunk`` and the final
            assembled string is returned.
        """
        llm = await self.get_llm()

        # Try streaming path first; fall back to non-streaming
        try:
            if stream and on_chunk:
                return await self._stream_chat(llm, dialogue, temperature, max_tokens, on_chunk)
            else:
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._sync_chat,
                    llm, dialogue, temperature, max_tokens,
                )
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            return f"[系统错误：LLM 调用失败 — {exc}]"

    def _sync_chat(self, llm, dialogue, temperature, max_tokens) -> str:
        # Attempt several common API shapes
        kwargs = {"messages": dialogue, "temperature": temperature, "max_tokens": max_tokens}
        try:
            resp = llm.chat(**kwargs)
        except TypeError:
            # Some providers use different kwarg names
            resp = llm.chat(dialogue, temperature=temperature, max_tokens=max_tokens)

        if hasattr(resp, "choices") and resp.choices:
            return resp.choices[0].message.content
        if isinstance(resp, str):
            return resp
        return json.dumps(resp, ensure_ascii=False) if resp else ""

    async def _stream_chat(
        self, llm, dialogue, temperature, max_tokens, on_chunk
    ) -> str:
        chunks: List[str] = []

        def _push(chunk_text: str):
            chunks.append(chunk_text)
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(chunk_text)
            asyncio.ensure_future(on_chunk(chunk_text))

        try:
            resp = llm.chat(
                messages=dialogue,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in resp:
                text = getattr(getattr(chunk, "choices", [None])[0], "delta", {}).get("content", "") if chunk and chunk.choices else ""
                if text:
                    _push(text)
        except Exception as exc:
            logger.error(f"Streaming LLM call failed: {exc}")
            return f"[流式调用失败：{exc}]"

        return "".join(chunks)


# ── MessageProcessor ─────────────────────────────────────────

class MessageProcessor:
    """Orchestrates conversation context, LLM calls, and response formatting."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.conversations: Dict[str, ConversationContext] = {}
        self.llm = LLMCaller(config)
        self.system_prompt = config.get("wechat", {}).get(
            "system_prompt", "你是一个有帮助的AI助手。"
        )

    def _get_or_create_context(self, user_id: str) -> ConversationContext:
        if user_id not in self.conversations:
            self.conversations[user_id] = ConversationContext(
                user_id=user_id,
                system_prompt=self.system_prompt,
            )
        return self.conversations[user_id]

    async def process_user_message(
        self,
        user_id: str,
        raw_wechat_msg: Dict[str, Any],
    ) -> NormalisedMessage:
        """Accept a raw WeChat message, produce an LLM-powered reply."""
        ctx = self._get_or_create_context(user_id)

        # 1. Normalise
        norm = normalise_wechat_message(raw_wechat_msg)
        ctx.add(norm)

        # 2. Call LLM
        dialogue = ctx.get_llm_dialogue()
        reply_text = await self.llm.chat(dialogue)

        # 3. Record assistant reply
        reply_msg = NormalisedMessage(
            role="assistant",
            content=reply_text,
            timestamp=datetime.now().timestamp(),
            metadata={"user_id": user_id},
        )
        ctx.add(reply_msg)

        logger.debug(f"User {user_id} → LLM reply: {reply_text[:80]}...")
        return reply_msg

    async def process_voice_message(
        self,
        user_id: str,
        voice_url: str,
        asr_text: Optional[str] = None,
    ) -> NormalisedMessage:
        """Handle voice messages — use ASR text if provided, otherwise delegate."""
        text = asr_text or f"[语音消息，URL: {voice_url}]"
        return await self.process_user_message(user_id, {"MsgType": "text", "Content": text})

    async def clear_context(self, user_id: str) -> bool:
        """Reset conversation history for a user."""
        if user_id in self.conversations:
            self.conversations[user_id].clear()
            del self.conversations[user_id]
            return True
        return False

    def get_context_info(self, user_id: str) -> Optional[dict]:
        ctx = self.conversations.get(user_id)
        if ctx is None:
            return None
        return {
            "user_id": ctx.user_id,
            "message_count": len(ctx.messages),
            "created_at": ctx.created_at,
            "last_interaction": ctx.last_interaction,
            "system_prompt": ctx.system_prompt,
        }
