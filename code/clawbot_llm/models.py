"""消息数据模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from enum import Enum


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"


@dataclass
class ContentBlock:
    """单个内容块"""
    type: ContentType
    value: str  # 文本内容 / 图片URL / 语音base64或URL


@dataclass
class Message:
    """对话消息"""
    role: MessageRole
    content_blocks: list[ContentBlock] = field(default_factory=list)
    timestamp: float = 0.0

    @property
    def text(self) -> str:
        """获取纯文本内容"""
        return " ".join(
            cb.value for cb in self.content_blocks if cb.type == ContentType.TEXT
        )

    @property
    def images(self) -> list[str]:
        return [cb.value for cb in self.content_blocks if cb.type == ContentType.IMAGE]

    @property
    def voice(self) -> str | None:
        for cb in self.content_blocks:
            if cb.type == ContentType.VOICE:
                return cb.value
        return None

    def add_text(self, text: str):
        self.content_blocks.append(ContentBlock(type=ContentType.TEXT, value=text))

    def add_image(self, url: str):
        self.content_blocks.append(ContentBlock(type=ContentType.IMAGE, value=url))

    def add_voice(self, data: str):
        self.content_blocks.append(ContentBlock(type=ContentType.VOICE, value=data))
