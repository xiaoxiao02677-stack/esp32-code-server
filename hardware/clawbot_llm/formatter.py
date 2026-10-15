"""消息格式转换：统一内部 Message 与各 LLM 提供商格式之间的互转"""
from __future__ import annotations
import base64
from typing import Any, Iterator

from models import Message, MessageRole, ContentType


class MessageFormatter:
    """消息格式转换器"""

    # ── 内部 Message → OpenAI 兼容格式 ──
    @staticmethod
    def to_openai_format(messages: list[Message]) -> list[dict]:
        """
        将内部 Message 列表转换为 OpenAI chat completions 格式。
        多模态内容（图片、语音）按 OpenAI vision 格式序列化。
        """
        result = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value}

            # 收集文本内容
            texts = [cb.value for cb in msg.content_blocks if cb.type == ContentType.TEXT]
            text_content = " ".join(texts).strip()

            # 收集图片和语音
            images = [cb.value for cb in msg.content_blocks if cb.type == ContentType.IMAGE]
            voices = [cb.value for cb in msg.content_blocks if cb.type == ContentType.VOICE]

            if msg.role == MessageRole.SYSTEM and not images and not voices:
                entry["content"] = text_content
            elif images or voices:
                # 多模态消息：构建 content array
                parts: list[dict] = []
                if text_content:
                    parts.append({"type": "text", "text": text_content})
                for img_url in images:
                    if img_url.startswith("http"):
                        parts.append({"type": "image_url", "image_url": {"url": img_url}})
                    else:
                        # base64 内嵌图片
                        ext = "png" if img_url.endswith(".png") else "jpeg"
                        b64 = base64.b64encode(open(img_url, "rb").read()).decode()
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{ext};base64,{b64}"},
                        })
                for voice_url in voices:
                    parts.append({
                        "type": "input_audio",
                        "input_audio": {"data": voice_url, "format": "wav"},
                    })
                entry["content"] = parts
            else:
                entry["content"] = text_content or ""

            result.append(entry)
        return result

    # ── OpenAI 格式响应 → 内部 Message ──
    @staticmethod
    def from_openai_format(response: dict, role: MessageRole = MessageRole.ASSISTANT) -> Message:
        """
        将 LLM 响应（OpenAI 格式）转换为内部 Message。
        兼容标准 OpenAI 响应和 Anthropic 格式。
        """
        msg = Message(role=role)
        inner = response.get("message", response)
        content = inner.get("content", "")
        if isinstance(content, list):
            # Anthropic 风格（content blocks）
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        msg.add_text(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        pass  # 跳过 thinking blocks
        elif isinstance(content, str):
            msg.add_text(content)
        return msg

    # ── 用户输入解析 ──
    @staticmethod
    def parse_user_input(text: str, image_urls: list[str] | None = None,
                         voice_data: str | None = None) -> Message:
        """将用户输入解析为 Message 对象"""
        msg = Message(role=MessageRole.USER)
        if text:
            msg.add_text(text)
        if image_urls:
            for url in image_urls:
                msg.add_image(url)
        if voice_data:
            msg.add_voice(voice_data)
        return msg

    # ── 上下文截断：保留最近 N 轮 + system ──
    @staticmethod
    def trim_messages(messages: list[Message], max_turns: int) -> list[Message]:
        """保留最近 max_turns 轮对话（system 消息始终保留）"""
        if max_turns <= 0:
            return messages

        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        user_assistant = [m for m in messages if m.role != MessageRole.SYSTEM]

        # 每轮 = 1 user + 1 assistant，取最近 max_turns * 2 条
        retained = user_assistant[-(max_turns * 2):]
        return system_msgs + retained

    # ── Token 预算估算 ──
    @staticmethod
    def estimate_tokens(messages: list[Message]) -> int:
        """
        粗略估算 token 数。
        经验规则：中文 1 字 ≈ 1 token，英文 1 词 ≈ 1 token。
        """
        total = 0
        for msg in messages:
            total += len(msg.text)  # 中文字符即 token 数
        return total

    @staticmethod
    def trim_by_tokens(messages: list[Message], max_tokens: int) -> list[Message]:
        """按 token 预算截断消息（从头移除旧消息）"""
        if max_tokens <= 0:
            return []

        # 始终保留 system 消息
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        non_system = [m for m in messages if m.role != MessageRole.SYSTEM]

        current_tokens = sum(len(m.text) for m in system_msgs)
        result = list(system_msgs)

        # 从尾部保留消息，直到超过预算
        for msg in reversed(non_system):
            msg_tokens = len(msg.text)
            if current_tokens + msg_tokens <= max_tokens:
                result.insert(len(system_msgs), msg)
                current_tokens += msg_tokens
            else:
                break

        result.reverse()
        return result
