"""设备配置云端记忆——工具调用拦截上报钩子（design-kawaii-console-v1 §1.2 链路②）

- DEVICE_CONFIG_TOOL_RULES：设备配置类工具白名单（契约源 design §5.2）。
  key 为 sanitize 后的工具名（core/utils/util.py sanitize_tool_name 把 "." 替换为 "_"）；
  新增设备配置项 = 固件加 MCP 工具 + 此表加一行 + 固件 ApplyDeviceConfig 加一个 case。
- on_tool_call：在 DeviceMCPExecutor.execute 入口调用；白名单匹配 → 参数校验
  （越界/类型不符丢弃并记日志）→ fire-and-forget 异步上报云端，失败只记日志，
  绝不阻塞/影响设备工具执行本身。
"""

import asyncio
from typing import Any, Dict, Optional, TYPE_CHECKING

from config.logger import setup_logging

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

# 设备配置工具白名单（契约源：design §5.2，与 Java 侧 DeviceConfigService 校验表保持一致）
# rule 字段：key=写入云端配置的键名；type=期望类型；min/max=值域（int 时生效）；
# param=工具参数中提取值的参数名
DEVICE_CONFIG_TOOL_RULES: Dict[str, Dict[str, Any]] = {
    "self_audio_speaker_set_volume": {
        "key": "volume",
        "type": int,
        "min": 0,
        "max": 100,
        "param": "volume",
    },
    "self_screen_set_brightness": {
        "key": "brightness",
        "type": int,
        "min": 0,
        "max": 100,
        "param": "brightness",
    },
    # P1 预留：self.screen.set_theme（enum light/dark）
}


def extract_config_from_arguments(rule: Dict[str, Any], arguments: Dict[str, Any]) -> Optional[Any]:
    """按规则从工具参数中提取并校验配置值；不合法返回 None（调用方丢弃）"""
    if not isinstance(arguments, dict):
        return None
    value = arguments.get(rule["param"])
    if value is None:
        return None
    expected_type = rule["type"]
    # bool 是 int 的子类，显式排除（True/False 不应被当作 1/0 记账）
    if isinstance(value, bool) or not isinstance(value, expected_type):
        return None
    if expected_type is int:
        if "min" in rule and value < rule["min"]:
            return None
        if "max" in rule and value > rule["max"]:
            return None
    return value


_REPORT_SEMAPHORE = asyncio.Semaphore(8)


async def _report_device_config_async(mac_address: str, config: Dict[str, Any]) -> None:
    """上报设备配置到云端（fire-and-forget 任务体；失败只记日志）"""
    from config.manage_api_client import report_device_config

    async with _REPORT_SEMAPHORE:
        await report_device_config(mac_address, config)


def on_tool_call(conn: "ConnectionHandler", tool_name: str, arguments: Dict[str, Any]) -> None:
    """设备配置工具拦截钩子——由 DeviceMCPExecutor.execute 入口调用

    - 非白名单工具：直接返回（零开销路径）
    - 白名单命中但参数缺失/类型不符/越界：丢弃上报并记日志（设备工具调用照常执行）
    - 合法值：asyncio.create_task 异步上报，不阻塞设备调用
    - 任何内部异常：仅记日志，绝不上抛影响工具执行
    """
    try:
        rule = DEVICE_CONFIG_TOOL_RULES.get(tool_name)
        if rule is None:
            return

        # P0 安全 gate（security-review）：未绑定或非 API 配置模式的连接不记账，
        # 防 MAC 伪造经未验证连接持久化篡改他人设备配置
        if getattr(conn, "need_bind", False) or not getattr(conn, "read_config_from_api", True):
            return
        # 裁决 b（2026-10，Kawaii 契约）：MQTT 网关透传连接上报与下发同时跳过，
        # 与 connection.py 下发侧 conn_from_mqtt_gateway 跳过对齐（design §6 风险4）
        if getattr(conn, "conn_from_mqtt_gateway", False):
            logger.bind(tag=TAG).info(
                f"设备配置上报跳过：工具 {tool_name} 来自MQTT网关连接（保守策略）"
            )
            return

        mac_address = getattr(getattr(conn, "headers", None), "get", lambda *_: None)("device-id")
        if not mac_address:
            logger.bind(tag=TAG).warning(
                f"设备配置上报跳过：工具 {tool_name} 的连接缺少 device-id"
            )
            return

        value = extract_config_from_arguments(rule, arguments)
        if value is None:
            logger.bind(tag=TAG).warning(
                f"设备配置上报丢弃：工具 {tool_name} 参数不合法 {arguments}"
            )
            return

        config = {rule["key"]: value}
        asyncio.create_task(_report_device_config_async(mac_address, config))
        logger.bind(tag=TAG).info(
            f"设备配置上报已调度：{mac_address} {config}（工具 {tool_name}）"
        )
    except Exception as e:
        logger.bind(tag=TAG).error(f"设备配置上报钩子异常（不影响工具执行）: {e}")
