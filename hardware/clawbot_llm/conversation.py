"""对话管理器：多轮上下文 + 持久化"""
from __future__ import annotations
import json
import time
import asyncio
from pathlib import Path
from typing import Any

from models import Message, MessageRole
from adapters import LLMAdapter
from formatter import MessageFormatter


class ConversationManager:
    """
    管理单个用户的完整对话上下文。

    功能：
    - 消息队列：按顺序追加/查询
    - 上下文截断：防止超出 token 限制
    - 历史持久化：保存到本地 JSON 文件
    """

    def __init__(self, user_id: str, storage_dir: str = "./conversations"):
        self.user_id = user_id
        self.messages: list[Message] = []
        self.storage_path = Path(storage_dir) / f"{user_id}.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # ── 消息操作 ──

    def add_message(self, message: Message):
        """追加消息到上下文"""
        message.timestamp = time.time()
        self.messages.append(message)

    def get_context(self, max_turns: int | None = None,
                    max_tokens: int = 4000) -> list[Message]:
        """
        获取对话上下文。
        max_turns: 最多保留多少轮对话（每轮 = 1 user + 1 assistant）
        max_tokens: 粗略的 token 预算（每条消息约 4 字符 = 1 token）
        """
        context = list(self.messages)

        if max_turns:
            context = MessageFormatter.trim_messages(context, max_turns)

        # 粗略 token 估算：中文字符 ≈ 1 token，英文单词 ≈ 1 token
        total_chars = sum(len(m.text) for m in context)
        if total_chars > max_tokens * 4:
            # 从尾部移除旧消息
            while total_chars > max_tokens * 4 and len(context) > 1:
                removed = context.pop(0)
                total_chars -= len(removed.text)

        return context

    def clear_context(self):
        """清空上下文并保存"""
        self.messages.clear()
        self._save()

    def get_history_summary(self) -> dict:
        """返回对话统计信息"""
        return {
            "user_id": self.user_id,
            "total_messages": len(self.messages),
            "turns": len([m for m in self.messages if m.role == MessageRole.USER]) // 2,
            "last_update": self.messages[-1].timestamp if self.messages else None,
        }

    # ── 持久化 ──

    def _save(self):
        """将上下文序列化为 JSON"""
        data = {
            "user_id": self.user_id,
            "messages": [
                {
                    "role": m.role.value,
                    "blocks": [
                        {"type": cb.type.value, "value": cb.value}
                        for cb in m.content_blocks
                    ],
                    "timestamp": m.timestamp,
                }
                for m in self.messages
            ],
        }
        self.storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _load(self):
        """从 JSON 文件加载上下文"""
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self.messages = []
            for entry in data.get("messages", []):
                msg = Message(
                    role=MessageRole(entry["role"]),
                    timestamp=entry.get("timestamp", 0.0),
                )
                for block in entry.get("blocks", []):
                    from models import ContentType
                    msg.content_blocks.append(
                        Message.ContentBlock(
                            type=ContentType(block["type"]),
                            value=block["value"],
                        )
                    )
                self.messages.append(msg)
        except (json.JSONDecodeError, KeyError, AttributeError):
            self.messages.clear()

    # ── 便捷方法：执行一次对话 ──

    async def chat(self, text: str, adapter: LLMAdapter,
                   system_prompt: str = "", max_turns: int = 10,
                   stream: bool = False, **kwargs) -> str | AsyncGenerator[str, None]:
        """
        发送用户消息、调用 LLM、更新上下文并返回回复。
        """
        from models import ContentType

        # 1. 构建用户消息
        user_msg = Message(role=MessageRole.USER)
        user_msg.add_text(text)
        self.add_message(user_msg)

        # 2. 获取格式化上下文
        context = self.get_context(max_turns=max_turns)
        if system_prompt:
            context = [Message(role=MessageRole.SYSTEM, content_blocks=[
                Message.ContentBlock(type=ContentType.TEXT, value=system_prompt)
            ])] + context

        openai_messages = MessageFormatter.to_openai_format(context)

        # 3. 调用 LLM
        if stream:
            async def _stream_wrapper():
                async for token in adapter.chat_stream(openai_messages, **kwargs):
                    yield token
                # 流式结束后收集完整响应再保存（简化处理）
            return _stream_wrapper()
        else:
            response = await adapter.chat(openai_messages, **kwargs)
            reply_msg = MessageFormatter.from_openai_format(response)
            self.add_message(reply_msg)
            self._save()
            return reply_msg.text

    async def chat_with_media(self, text: str, image_urls: list[str] | None = None,
                              voice_data: str | None = None,
                              adapter: LLMAdapter, system_prompt: str = "",
                              max_turns: int = 10, **kwargs) -> str:
        """支持图片/语音的多模态对话"""
        from models import ContentType

        user_msg = MessageFormatter.parse_user_input(
            text=text, image_urls=image_urls, voice_data=voice_data
        )
        self.add_message(user_msg)

        context = self.get_context(max_turns=max_turns)
        if system_prompt:
            context = [Message(role=MessageRole.SYSTEM, content_blocks=[
                Message.ContentBlock(type=ContentType.TEXT, value=system_prompt)
            ])] + context

        openai_messages = MessageFormatter.to_openai_format(context)
        response = await adapter.chat(openai_messages, **kwargs)
        reply_msg = MessageFormatter.from_openai_format(response)
        self.add_message(reply_msg)
        self._save()
        return reply_msg.text
