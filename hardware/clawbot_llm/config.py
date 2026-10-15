"""
配置管理：从 YAML 文件加载 LLM 相关配置。
支持热重载和默认值兜底。
"""
from __future__ import annotations
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMConfig:
    """LLM 运行时配置"""
    provider: str = "deepseek"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2000
    base_url: str | None = None
    timeout: float = 60.0

    # 多轮对话参数
    conversation_max_turns: int = 10
    conversation_context_window: int = 4000

    # 系统提示词
    system_prompt: str = "你是一个 helpful 的 AI 助手。"

    # 流式输出开关
    stream: bool = False

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class AppConfig:
    """完整应用配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage_dir: str = "./conversations"
    log_level: str = "INFO"


class ConfigManager:
    """配置管理器，支持从 YAML 文件加载"""

    _instance: ConfigManager | None = None

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = AppConfig()

    @classmethod
    def load(cls, config_path: str = "config.yaml") -> ConfigManager:
        """单例模式：全局唯一配置实例"""
        if cls._instance is None:
            cls._instance = cls(config_path)
            cls._instance._reload()
        else:
            cls._instance.config_path = config_path
            cls._instance._reload()
        return cls._instance

    def _reload(self):
        """重新加载配置文件"""
        if not self.config_path.exists():
            return
        with open(self.config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        self._config = AppConfig()
        self._load_llm(raw.get("llm", {}))
        if "storage_dir" in raw:
            self._config.storage_dir = raw["storage_dir"]
        if "log_level" in raw:
            self._config.log_level = raw["log_level"]

    def _load_llm(self, llm_raw: dict):
        llm = LLMConfig(
            provider=llm_raw.get("provider", "deepseek"),
            api_key=llm_raw.get("api_key", ""),
            model=llm_raw.get("model", "deepseek-chat"),
            temperature=float(llm_raw.get("temperature", 0.7)),
            max_tokens=int(llm_raw.get("max_tokens", 2000)),
            base_url=llm_raw.get("base_url"),
            timeout=float(llm_raw.get("timeout", 60.0)),
            conversation_max_turns=int(llm_raw.get("conversation", {}).get("max_turns", 10)),
            conversation_context_window=int(llm_raw.get("conversation", {}).get("context_window", 4000)),
            system_prompt=llm_raw.get("system_prompt", "你是一个 helpful 的 AI 助手。"),
            stream=bool(llm_raw.get("stream", False)),
        )
        self._config.llm = llm

    @property
    def llm(self) -> LLMConfig:
        return self._config.llm

    @property
    def storage_dir(self) -> str:
        return self._config.storage_dir

    def reload(self):
        """手动触发重新加载"""
        self._reload()
