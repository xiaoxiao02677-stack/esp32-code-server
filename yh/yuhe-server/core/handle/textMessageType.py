from enum import Enum


class TextMessageType(Enum):
    """消息类型枚举"""
    HELLO = "hello"
    ABORT = "abort"
    LISTEN = "listen"
    IOT = "iot"
    MCP = "mcp"
    SERVER = "server"
    PING = "ping"
    WALLPAPER = "wallpaper"
    # 设备本地配置上报（物理音量/亮度键）：固件 SendDeviceConfigReport 主动上行
    DEVICE_CONFIG_REPORT = "device_config_report"
