from typing import Any, Dict

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType

TAG = __name__

# 与 Java DeviceConfigServiceImpl.CONFIG_KEYS 数值子集对齐（本消息只上报数值型，
# 唤醒词/打断开关仍走 MCP 工具路径，不在此列）
_NUMERIC_KEYS = {"volume": (0, 100), "brightness": (0, 100)}


class DeviceConfigReportHandler(TextMessageHandler):
    """设备本地配置上报处理器（物理音量/亮度键同步云端）

    背景：语音调整走 MCP 工具（self.audio_speaker.set_volume 等），由
    device_config_sync.on_tool_call 拦截上报云端；物理按键路径没有 MCP 调用，
    此前只改本地 NVS，云端 ai_device_config 永远是旧值——管理台改一次音量
    会把设备物理键的调整顶回去。

    固件侧（application.cc SendDeviceConfigReport）在音量/亮度键回调里主动上行：
    ``{"type":"device_config_report","config":{"volume":60}}``

    本 handler 复用 MCP 路径同一条云端链路（manage_api_client.report_device_config
    → Java POST /config/device-config → ai_device_config），安全 gate 与
    device_config_sync.on_tool_call 保持一致：
    - 未绑定连接（need_bind）不记账，防 MAC 伪造篡改他人设备配置
    - MQTT 网关透传连接跳过（保守策略，与上报/下发两侧既有裁决对齐）
    - fire-and-forget：上报失败只记日志，不影响设备连接
    """

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.DEVICE_CONFIG_REPORT

    async def handle(self, conn, msg_json: Dict[str, Any]) -> None:
        config = msg_json.get("config")
        if not isinstance(config, dict) or not config:
            conn.logger.bind(tag=TAG).warning(
                f"忽略 device_config_report：config 非法 {msg_json}"
            )
            return

        # 与 device_config_sync.on_tool_call 相同的安全 gate
        if getattr(conn, "need_bind", False) or not getattr(
            conn, "read_config_from_api", True
        ):
            conn.logger.bind(tag=TAG).info(
                "设备配置上报跳过：连接未绑定或非 API 配置模式（保守策略）"
            )
            return
        if getattr(conn, "conn_from_mqtt_gateway", False):
            conn.logger.bind(tag=TAG).info(
                "设备配置上报跳过：来自 MQTT 网关连接（保守策略）"
            )
            return

        device_id = getattr(conn, "device_id", None) or ""
        if not device_id:
            conn.logger.bind(tag=TAG).warning(
                f"设备配置上报跳过：连接缺少 device_id {msg_json}"
            )
            return

        # 白名单 + 范围校验（与 Java sanitizeConfig 数值分支一致）
        delta: Dict[str, int] = {}
        for key, value in config.items():
            rule = _NUMERIC_KEYS.get(key)
            if rule is None:
                conn.logger.bind(tag=TAG).warning(
                    f"设备配置上报丢弃：非白名单键 {key}={value}"
                )
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                conn.logger.bind(tag=TAG).warning(
                    f"设备配置上报丢弃：{key}={value} 类型非法"
                )
                continue
            if not (rule[0] <= value <= rule[1]):
                conn.logger.bind(tag=TAG).warning(
                    f"设备配置上报丢弃：{key}={value} 越界 [{rule[0]},{rule[1]}]"
                )
                continue
            delta[key] = value

        if not delta:
            conn.logger.bind(tag=TAG).warning(
                f"设备配置上报丢弃：无合法键 {msg_json}"
            )
            return

        try:
            # 复用 MCP 工具路径的异步上报通道（含并发信号量与失败静默）
            from core.providers.tools.device_config_sync import (
                _report_device_config_async,
            )

            import asyncio

            asyncio.create_task(_report_device_config_async(device_id, delta))
            conn.logger.bind(tag=TAG).info(
                f"设备配置上报已调度：device={device_id} {delta}（物理键路径）"
            )
        except Exception as e:
            conn.logger.bind(tag=TAG).error(f"设备配置上报调度异常: {e}")
