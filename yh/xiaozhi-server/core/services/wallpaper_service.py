#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壁纸即时下发服务

由 HTTP API ``POST /api/wallpaper/dispatch`` 调用，向在线设备的既有 WS 连接
下发壁纸设置指令：

    {"type":"wallpaper","action":"set","version":"3","url":"...",
     "md5":"...","size":115200,"format":"rgb565"}

投递策略（对齐 push_scheduler 的三级降级）：
- 设备 WS 在线：直投 ``{"type":"wallpaper",...}``。
- 设备 WS 不在线（固件 2.5.x 心跳常驻、WS 按需建立，心跳在线≠WS 在线）：
  指令入**离线补投队列**，设备 WS 建立（hello 注册）时由
  ``on_connection_registered`` 自动补投；同时 device_config 路径仍保证
  「下次启动生效」双保险。
- ``need_bind``（未绑定）与 ``conn_from_mqtt_gateway``（MQTT 网关设备）的连接
  无法直接投递固件消息，记入 ``offline`` 并记录原因（不入队）。
- 不按固件能力过滤：老固件不识别 ``type:"wallpaper"`` 会在固件侧静默丢弃，
  服务端照发（见 P1-3 兼容性约定）。

返回体：``{"sent": [...], "queued": [...], "offline": [...]}``；
``queued`` 为已入队待补投设备（Java 侧显示为 pending + 排队文案）。
队列存于进程内存：服务重启即丢，但 device_config 兜底语义不受影响。
"""
import asyncio
import json
import logging

from core.utils.stdlib_log_bridge import install_stdlib_log_bridge

logger = logging.getLogger(__name__)
install_stdlib_log_bridge(__name__)

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
        # WakeWordService：提供心跳服务引用（心跳 TCP 通道兜底下发）
        self._wake_word_service = None
        # 离线补投队列：{device_id: [msg_dict, ...]}，设备 WS 上线时补投
        self._offline_queue: dict = {}
        self._queue_lock = asyncio.Lock()
        logger.info("WallpaperService 初始化完成")

    def bind_connections_provider(self, provider) -> None:
        """绑定连接快照提供者（通常是 wake_word_service.get_connections）。"""
        self._connections_provider = provider

    def bind_wake_word_service(self, wake_word_service) -> None:
        """注入 WakeWordService：取其 heartbeat_server 作为无 WS 时的下发通道。"""
        self._wake_word_service = wake_word_service

    def _find_heartbeat_device(self, device_id: str):
        """在心跳设备表按归一化 ID 匹配，返回 (hb_device_id, info) 或 None。"""
        hb = getattr(self._wake_word_service, "heartbeat_server", None)
        if hb is None:
            return None
        target = _normalize_device_id(device_id)
        if not target:
            return None
        try:
            for hb_did, info in hb.devices.items():
                if _normalize_device_id(hb_did) == target:
                    return hb_did, info
        except Exception:
            return None
        return None

    async def _dispatch_via_heartbeat(self, device_id: str, msg: dict) -> bool:
        """无 WS 连接时经心跳 TCP 通道下发 SET_WALLPAPER。

        设备空闲态不保持 WS（按次会话），但心跳通道常连；固件需在
        ADVERTISEMENT 里声明 SET_WALLPAPER 能力才走这条路径，否则返回 False
        交由离线补投队列处理。
        """
        match = self._find_heartbeat_device(device_id)
        if match is None:
            return False
        hb_did, info = match
        if not info.get("online"):
            return False
        hb = getattr(self._wake_word_service, "heartbeat_server", None)
        if hb is None or not hb.supports_operation(hb_did, "SET_WALLPAPER"):
            return False
        parameters = {
            "version": msg.get("version", ""),
            "url": msg.get("url", ""),
            "md5": msg.get("md5", ""),
            "size": msg.get("size", 0),
            "format": msg.get("format", "rgb565"),
        }
        ok = await hb.send_to_device(hb_did, "SET_WALLPAPER", parameters)
        if ok:
            logger.info(
                f"壁纸经心跳通道下发: device={device_id} hb={hb_did} "
                f"version={msg.get('version')}"
            )
        return ok

    async def on_connection_registered(self, device_id: str, conn) -> None:
        """设备 WS 上线（hello 注册）钩子：补投该设备排队的壁纸指令。

        由 wake_word_service.register_connection 调用；失败的消息重新入队。
        """
        async with self._queue_lock:
            pending = self._offline_queue.pop(device_id, [])
        if not pending:
            return
        if getattr(conn, "need_bind", False) or getattr(
            conn, "conn_from_mqtt_gateway", False
        ):
            logger.info(
                f"壁纸补投放弃：设备 {device_id} 未绑定或来自MQTT网关，"
                f"丢弃 {len(pending)} 条排队指令"
            )
            return
        logger.info(f"设备 {device_id} 文本通道上线，补投 {len(pending)} 条壁纸指令")
        failed = []
        for msg in pending:
            payload = json.dumps(msg, ensure_ascii=False)
            if await self._send_to_conn(device_id, conn, payload):
                logger.info(
                    f"壁纸补投成功: device={device_id} version={msg.get('version')}"
                )
            else:
                failed.append(msg)
        if failed:
            async with self._queue_lock:
                self._offline_queue.setdefault(device_id, []).extend(failed)

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
            {"sent": [device_id, ...], "queued": [device_id, ...],
             "offline": [device_id, ...]}
            - sent:   WS 在线，已直投（设备会回 result 回执）
            - queued: WS 不在线，已入离线补投队列，设备文本通道建立后自动下发
            - offline: 未绑定 / MQTT 网关 / 发送失败且无法排队，仅落 device_config
        """
        msg = build_wallpaper_message(wallpaper)
        payload = json.dumps(msg, ensure_ascii=False)
        connections = self._snapshot_connections()
        logger.info(f"壁纸下发开始: version={msg['version']} 目标设备数={len(device_ids)}")

        sent, queued, offline = [], [], []
        for device_id in device_ids:
            conn = self._lookup(connections, device_id)
            if conn is None:
                # 无 WS：优先走常连的心跳 TCP 通道（固件声明 SET_WALLPAPER 才可用）
                if await self._dispatch_via_heartbeat(device_id, msg):
                    sent.append(device_id)
                    continue
                # 心跳通道也不可用：入离线补投队列
                async with self._queue_lock:
                    self._offline_queue.setdefault(device_id, []).append(dict(msg))
                logger.info(
                    f"壁纸下发排队：设备 {device_id} WS 与心跳通道均不可直投，待其上线补投"
                )
                queued.append(device_id)
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
                # 直投失败（连接可能正在断开）：同样入队等待补投
                async with self._queue_lock:
                    self._offline_queue.setdefault(device_id, []).append(dict(msg))
                queued.append(device_id)

        logger.info(
            f"壁纸下发完成: version={msg['version']} sent={len(sent)} "
            f"queued={len(queued)} offline={len(offline)}"
        )
        return {"sent": sent, "queued": queued, "offline": offline}

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
