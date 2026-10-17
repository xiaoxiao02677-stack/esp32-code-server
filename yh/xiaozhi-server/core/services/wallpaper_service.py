#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壁纸即时下发服务

由 HTTP API ``POST /api/wallpaper/dispatch`` 调用，向在线设备的既有 WS 连接
下发壁纸设置指令：

    {"type":"wallpaper","action":"set","version":"3","url":"...",
     "md5":"...","size":115200,"format":"rgb565"}

投递策略（与 wake_word_service / push_scheduler 保持一致）：
- 只走设备 WS 连接直发；WS 不在线的设备记入 ``offline``，不落离线队列
  （壁纸是版本化资源，设备下次上线会重新拉取最新版本，补推旧版本无意义）。
- ``need_bind``（未绑定）与 ``conn_from_mqtt_gateway``（MQTT 网关设备）的连接
  无法直接投递固件消息，同样记入 ``offline`` 并记录原因。
- 不按固件能力过滤：老固件不识别 ``type:"wallpaper"`` 会在固件侧静默丢弃，
  服务端照发（见 P1-3 兼容性约定）。
"""
import json
import logging

logger = logging.getLogger(__name__)

TAG = __name__


def _normalize_device_id(device_id: str) -> str:
    """归一化设备 ID，用于兼容 MAC 冒号格式与 xiaozhi- 前缀格式。

    ``14:c1:9f:d1:33:48`` / ``14-c1-9f-d1-33-48`` /
    ``xiaozhi-14c19fd13348`` / ``14c19fd13348`` → ``14c19fd13348``
    """
    if not device_id:
        return ""
    value = str(device_id).strip().lower()
    if value.startswith("xiaozhi-"):
        value = value[len("xiaozhi-"):]
    return value.replace(":", "").replace("-", "")


def build_wallpaper_message(wallpaper: dict) -> dict:
    """构造下发给设备的壁纸 WS 文本消息（字段与固件约定一致）。"""
    try:
        size = int(wallpaper.get("size", 0) or 0)
    except (TypeError, ValueError):
        size = 0
    return {
        "type": "wallpaper",
        "action": "set",
        "version": str(wallpaper.get("version", "")),
        "url": wallpaper.get("url", ""),
        "md5": wallpaper.get("md5", ""),
        "size": size,
        "format": wallpaper.get("format", "rgb565"),
    }


class WallpaperService:
    """壁纸下发服务，由 app.py 构造并注入 SimpleHttpServer。"""

    def __init__(self):
        # 连接快照提供者：返回 {device_id: ConnectionHandler}
        self._connections_provider = None
        logger.info("WallpaperService 初始化完成")

    def bind_connections_provider(self, provider) -> None:
        """绑定连接快照提供者（通常是 wake_word_service.get_connections）。"""
        self._connections_provider = provider

    def _snapshot_connections(self) -> dict:
        if self._connections_provider is None:
            return {}
        try:
            return dict(self._connections_provider() or {})
        except Exception as e:
            logger.error(f"获取设备连接快照失败: {e}")
            return {}

    def _lookup(self, connections: dict, device_id: str):
        """按 device_id 找连接：先精确匹配，再按归一化 ID 兜底。"""
        conn = connections.get(device_id)
        if conn is not None:
            return conn
        target = _normalize_device_id(device_id)
        if not target:
            return None
        for key, candidate in connections.items():
            if _normalize_device_id(key) == target:
                return candidate
        return None

    async def dispatch(self, device_ids, wallpaper: dict) -> dict:
        """向指定设备下发壁纸设置指令。

        Returns:
            {"sent": [device_id, ...], "offline": [device_id, ...]}
        """
        msg = build_wallpaper_message(wallpaper)
        payload = json.dumps(msg, ensure_ascii=False)
        connections = self._snapshot_connections()
        logger.info(f"壁纸下发开始: version={msg['version']} 目标设备数={len(device_ids)}")

        sent, offline = [], []
        for device_id in device_ids:
            conn = self._lookup(connections, device_id)
            if conn is None:
                logger.info(f"壁纸下发跳过：设备 {device_id} WS 不在线")
                offline.append(device_id)
                continue
            if getattr(conn, "need_bind", False) or getattr(
                conn, "conn_from_mqtt_gateway", False
            ):
                logger.info(
                    f"壁纸下发跳过：设备 {device_id} 未绑定或来自MQTT网关，无法直投"
                )
                offline.append(device_id)
                continue
            if await self._send_to_conn(device_id, conn, payload):
                sent.append(device_id)
            else:
                offline.append(device_id)

        logger.info(
            f"壁纸下发完成: version={msg['version']} sent={len(sent)} offline={len(offline)}"
        )
        return {"sent": sent, "offline": offline}

    async def _send_to_conn(self, device_id: str, conn, payload: str) -> bool:
        """向单台设备 WS 连接发送文本消息，失败返回 False。"""
        try:
            ws = getattr(conn, "websocket", None)
            if ws is None:
                logger.warning(f"设备 {device_id} 的 websocket 为 None，跳过壁纸下发")
                return False
            closed = False
            if hasattr(ws, "closed") and ws.closed:
                closed = True
            elif hasattr(ws, "state") and getattr(ws.state, "name", "") == "CLOSED":
                closed = True
            if closed:
                logger.warning(f"设备 {device_id} 连接已关闭，跳过壁纸下发")
                return False
            await ws.send(payload)
            logger.info(f"已向设备 {device_id} 下发壁纸设置指令")
            return True
        except Exception as e:
            logger.error(f"向设备 {device_id} 下发壁纸失败: {e}")
            return False
