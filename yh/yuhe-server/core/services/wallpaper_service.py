#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壁纸即时下发服务

由 HTTP API ``POST /api/wallpaper/dispatch`` 调用，向在线设备的既有 WS 连接
下发壁纸设置指令：

    {"type":"wallpaper","action":"set","version":"3-<md5>","url":"...",
     "md5":"...","size":115200,"format":"rgb565"}

投递策略（对齐 push_scheduler 的三级降级）：
- 设备 WS 在线：直投 ``{"type":"wallpaper",...}``。
- 设备 WS 不在线但心跳 TCP 常连且 ADVERTISEMENT 声明了 ``SET_WALLPAPER``：
  经心跳通道下发 ``COMMAND/SET_WALLPAPER``。
- 两条通道都不可用：指令入**待补投队列**，由以下三个触发点自动重投，任一成功即出队：
  1. 设备 WS 建立（hello 注册）→ ``on_connection_registered``；
  2. 设备心跳重连/恢复在线 → ``on_device_online``（heartbeat_server 回调）；
  3. 后台巡检 ``sweeper``（默认 30s 一轮，覆盖前两个钩子漏掉的情况）。
- ``need_bind``（未绑定）与 ``conn_from_mqtt_gateway``（MQTT 网关设备）的连接
  无法直接投递固件消息，记入 ``offline`` 并记录原因（不入队）。
- 不按固件能力过滤：老固件不识别 ``type:"wallpaper"`` 会在固件侧静默丢弃，
  服务端照发（见 P1-3 兼容性约定）。

队列语义：**每设备仅保留最新一条**（壁纸下发是幂等的 last-write-wins），
避免用户连点多次下发后设备一次上线被灌多条指令、重复下载同一张图。
队列同时落 Redis（``wallpaper:pending:<归一化设备ID>``，TTL 7 天）作为进程重启
的兜底；Redis 不可用时退化为纯内存（行为与旧版一致）。

返回体：``{"sent": [...], "queued": [...], "offline": [...]}``；
``queued`` 为已入队待补投设备（Java 侧显示为 pending + 排队文案）。
"""
import asyncio
import json
import logging
import time

from core.utils.stdlib_log_bridge import install_stdlib_log_bridge

logger = logging.getLogger(__name__)
install_stdlib_log_bridge(__name__)

TAG = __name__

# 队列条目保留上限：与回执 TTL 对齐，超期视为「设备长期不上线」直接丢弃
QUEUE_TTL_SECONDS = 7 * 24 * 60 * 60
# 后台巡检间隔
SWEEP_INTERVAL_SECONDS = 30
# Redis key 前缀（值为单条记录的 JSON）
QUEUE_KEY_PREFIX = "wallpaper:pending:"


def _normalize_device_id(device_id: str) -> str:
    """归一化设备 ID，用于兼容 MAC 冒号格式与 yuhe- 前缀格式。

    ``14:c1:9f:d1:33:48`` / ``14-c1-9f-d1-33-48`` /
    ``yuhe-14c19fd13348`` / ``14c19fd13348`` → ``14c19fd13348``
    """
    if not device_id:
        return ""
    value = str(device_id).strip().lower()
    if value.startswith("yuhe-"):
        value = value[len("yuhe-"):]
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
        # 全局 config（取 config["redis"] 做队列持久化）
        self._config = None
        # 待补投队列：{device_id: {"msg": {...}, "ts": epoch, "attempts": int}}
        # 每设备只保留最新一条：壁纸下发幂等，旧指令被新指令覆盖
        self._offline_queue: dict = {}
        self._queue_lock = asyncio.Lock()
        self._sweeper_task = None
        self._redis_warned = False
        logger.info("WallpaperService 初始化完成")

    # ------------------------------------------------------------------ 装配

    def bind_connections_provider(self, provider) -> None:
        """绑定连接快照提供者（通常是 wake_word_service.get_connections）。"""
        self._connections_provider = provider

    def bind_wake_word_service(self, wake_word_service) -> None:
        """注入 WakeWordService：取其 heartbeat_server 作为无 WS 时的下发通道。"""
        self._wake_word_service = wake_word_service

    def bind_config(self, config: dict) -> None:
        """注入全局配置，用于待补投队列的 Redis 持久化。"""
        self._config = config or {}

    # ------------------------------------------------------------------ 队列

    async def _redis(self):
        """取 Redis 客户端（复用 wallpaper_ack 的连接），不可用返回 None。"""
        if not self._config:
            return None
        try:
            from core.utils.wallpaper_ack import get_client

            return await get_client(self._config)
        except Exception as e:  # 任何异常都退化为纯内存队列
            if not self._redis_warned:
                self._redis_warned = True
                logger.warning(f"壁纸队列 Redis 不可用，降级为内存队列: {e}")
            return None

    async def _persist(self, device_id: str, record: dict) -> None:
        client = await self._redis()
        if client is None:
            return
        key = f"{QUEUE_KEY_PREFIX}{_normalize_device_id(device_id)}"
        try:
            await client.set(
                key,
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                ex=QUEUE_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(f"壁纸队列落 Redis 失败 device={device_id}: {e}")

    async def _forget(self, device_id: str) -> None:
        client = await self._redis()
        if client is None:
            return
        try:
            await client.delete(f"{QUEUE_KEY_PREFIX}{_normalize_device_id(device_id)}")
        except Exception as e:
            logger.warning(f"壁纸队列清理失败 device={device_id}: {e}")

    async def hydrate(self) -> int:
        """启动时从 Redis 恢复待补投队列，返回恢复条数。"""
        client = await self._redis()
        if client is None:
            return 0
        restored = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor, match=f"{QUEUE_KEY_PREFIX}*", count=200
                )
                for key in keys:
                    raw = await client.get(key)
                    if not raw:
                        continue
                    try:
                        record = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    msg = record.get("msg") or {}
                    device_id = msg.get("_device_id") or str(key).split(
                        QUEUE_KEY_PREFIX, 1
                    )[-1]
                    ts = float(record.get("ts") or 0)
                    if time.time() - ts > QUEUE_TTL_SECONDS:
                        await client.delete(key)
                        continue
                    async with self._queue_lock:
                        self._offline_queue[device_id] = {
                            "msg": msg,
                            "ts": ts,
                            "attempts": int(record.get("attempts") or 0),
                        }
                    restored += 1
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"壁纸队列恢复失败: {e}")
            return restored
        if restored:
            logger.info(f"壁纸队列已从 Redis 恢复 {restored} 条待补投指令")
        return restored

    async def _enqueue(self, device_id: str, msg: dict) -> bool:
        """入队（last-write-wins）。同版本已在队列中则视为重复，不重复计数。

        Returns:
            True 表示这是一条新指令（版本变化），False 表示同版本重复下发。
        """
        payload = dict(msg)
        payload["_device_id"] = device_id
        normalized = _normalize_device_id(device_id)
        async with self._queue_lock:
            existing = None
            for key in list(self._offline_queue.keys()):
                if _normalize_device_id(key) == normalized:
                    existing = self._offline_queue.pop(key)
                    break
            if existing is not None:
                old_version = str((existing.get("msg") or {}).get("version", ""))
                if old_version == payload.get("version"):
                    # 同版本重发：保留原入队时间，避免设备长期不在线时 TTL 被无限续期
                    self._offline_queue[device_id] = existing
                    is_new = False
                else:
                    self._offline_queue[device_id] = {
                        "msg": payload,
                        "ts": time.time(),
                        "attempts": 0,
                    }
                    is_new = True
            else:
                self._offline_queue[device_id] = {
                    "msg": payload,
                    "ts": time.time(),
                    "attempts": 0,
                }
                is_new = True
            record = self._offline_queue[device_id]
        await self._persist(device_id, record)
        if not is_new:
            logger.info(
                f"壁纸下发：设备 {device_id} 已有同版本排队指令，跳过重复入队 "
                f"version={payload.get('version')}"
            )
        return is_new

    async def _dequeue(self, device_id: str) -> None:
        normalized = _normalize_device_id(device_id)
        async with self._queue_lock:
            for key in list(self._offline_queue.keys()):
                if _normalize_device_id(key) == normalized:
                    self._offline_queue.pop(key, None)
        await self._forget(device_id)

    def queue_snapshot(self) -> dict:
        """调试用：返回当前待补投队列的浅拷贝 {device_id: version}。"""
        return {
            k: str((v.get("msg") or {}).get("version", ""))
            for k, v in list(self._offline_queue.items())
        }

    # ------------------------------------------------------------------ 通道

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
        交由待补投队列处理。
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

    def _conn_undeliverable(self, conn) -> bool:
        """未绑定 / MQTT 网关代连的连接无法投递固件消息。"""
        return bool(
            getattr(conn, "need_bind", False)
            or getattr(conn, "conn_from_mqtt_gateway", False)
        )

    async def _try_deliver(self, device_id: str, msg: dict) -> bool:
        """按 WS → 心跳 TCP 的顺序尝试投递一条指令，成功返回 True。"""
        conn = self._lookup(self._snapshot_connections(), device_id)
        if conn is not None:
            if self._conn_undeliverable(conn):
                return False
            payload = json.dumps(msg, ensure_ascii=False)
            if await self._send_to_conn(device_id, conn, payload):
                return True
        return await self._dispatch_via_heartbeat(device_id, msg)

    # ------------------------------------------------------------------ 触发点

    async def on_connection_registered(self, device_id: str, conn) -> None:
        """设备 WS 上线（hello 注册）钩子：补投该设备排队的壁纸指令。

        由 wake_word_service.register_connection 调用；失败则在巡检里重试。
        """
        normalized = _normalize_device_id(device_id)
        record = None
        async with self._queue_lock:
            for key in list(self._offline_queue.keys()):
                if _normalize_device_id(key) == normalized:
                    record = self._offline_queue.get(key)
                    break
        if not record:
            return
        if self._conn_undeliverable(conn):
            logger.info(
                f"壁纸补投放弃：设备 {device_id} 未绑定或来自MQTT网关，"
                f"丢弃排队指令 version={record['msg'].get('version')}"
            )
            await self._dequeue(device_id)
            return
        msg = record.get("msg") or {}
        msg.pop("_device_id", None)
        logger.info(
            f"设备 {device_id} 文本通道上线，补投壁纸指令 version={msg.get('version')}"
        )
        payload = json.dumps(msg, ensure_ascii=False)
        if await self._send_to_conn(device_id, conn, payload):
            await self._dequeue(device_id)
            logger.info(f"壁纸补投成功: device={device_id} version={msg.get('version')}")

    async def on_device_online(self, device_id: str) -> None:
        """设备心跳重连/恢复在线钩子：立即尝试补投（不必等巡检周期）。"""
        normalized = _normalize_device_id(device_id)
        record = None
        async with self._queue_lock:
            for key in list(self._offline_queue.keys()):
                if _normalize_device_id(key) == normalized:
                    record = self._offline_queue.get(key)
                    break
        if not record:
            return
        msg = dict(record.get("msg") or {})
        msg.pop("_device_id", None)
        if await self._dispatch_via_heartbeat(device_id, msg):
            await self._dequeue(device_id)
            logger.info(
                f"壁纸补投成功（心跳通道）: device={device_id} version={msg.get('version')}"
            )

    async def sweep_once(self) -> int:
        """巡检一轮：尝试投递所有排队指令，返回本轮成功条数。"""
        now = time.time()
        snapshot = list(self._offline_queue.items())
        delivered = 0
        for device_id, record in snapshot:
            if now - float(record.get("ts") or 0) > QUEUE_TTL_SECONDS:
                logger.info(f"壁纸排队超期丢弃: device={device_id}")
                await self._dequeue(device_id)
                continue
            msg = dict(record.get("msg") or {})
            msg.pop("_device_id", None)
            record["attempts"] = int(record.get("attempts") or 0) + 1
            try:
                ok = await self._try_deliver(device_id, msg)
            except Exception as e:
                logger.error(f"壁纸巡检投递异常 device={device_id}: {e}")
                ok = False
            if ok:
                await self._dequeue(device_id)
                delivered += 1
                logger.info(
                    f"壁纸巡检补投成功: device={device_id} "
                    f"version={msg.get('version')} attempts={record['attempts']}"
                )
            else:
                await self._persist(device_id, record)
        return delivered

    async def _sweep_loop(self, interval: float) -> None:
        logger.info(f"壁纸补投巡检已启动，周期 {interval:.0f}s")
        while True:
            try:
                await asyncio.sleep(interval)
                pending = len(self._offline_queue)
                if pending:
                    delivered = await self.sweep_once()
                    logger.info(
                        f"壁纸巡检: 待补投={pending} 本轮成功={delivered} "
                        f"剩余={len(self._offline_queue)}"
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"壁纸巡检循环异常: {e}")

    async def start_sweeper(self, interval: float = SWEEP_INTERVAL_SECONDS) -> None:
        """启动后台补投巡检（幂等），并把 Redis 中的队列恢复到内存。"""
        await self.hydrate()
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweep_loop(interval))

    async def stop(self) -> None:
        if self._sweeper_task is not None:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except Exception:
                pass
            self._sweeper_task = None

    # ------------------------------------------------------------------ 下发

    async def dispatch(self, device_ids, wallpaper: dict) -> dict:
        """向指定设备下发壁纸设置指令。

        Returns:
            {"sent": [device_id, ...], "queued": [device_id, ...],
             "offline": [device_id, ...]}
            - sent:   已投递（WS 直投或心跳通道），设备会回 result 回执
            - queued: 两条通道均不可用，已入待补投队列，设备上线后自动下发
            - offline: 未绑定 / MQTT 网关 / 无 MAC，仅落 device_config
        """
        msg = build_wallpaper_message(wallpaper)
        payload = json.dumps(msg, ensure_ascii=False)
        connections = self._snapshot_connections()
        logger.info(f"壁纸下发开始: version={msg['version']} 目标设备数={len(device_ids)}")

        sent, queued, offline = [], [], []
        for device_id in device_ids:
            conn = self._lookup(connections, device_id)
            if conn is not None and not self._conn_undeliverable(conn):
                if await self._send_to_conn(device_id, conn, payload):
                    sent.append(device_id)
                    continue
            elif conn is not None:
                logger.info(
                    f"壁纸下发跳过：设备 {device_id} 未绑定或来自MQTT网关，无法直投"
                )
                offline.append(device_id)
                continue

            # 无可用 WS：优先走常连的心跳 TCP 通道
            if await self._dispatch_via_heartbeat(device_id, msg):
                sent.append(device_id)
                continue

            # 两条通道都不可用：入待补投队列（last-write-wins）
            await self._enqueue(device_id, msg)
            logger.info(
                f"壁纸下发排队：设备 {device_id} WS 与心跳通道均不可直投，待其上线补投"
            )
            queued.append(device_id)

        logger.info(
            f"壁纸下发完成: version={msg['version']} sent={len(sent)} "
            f"queued={len(queued)} offline={len(offline)}"
        )
        # ★ 清掉这批设备的历史排队记录。
        #   以前只有 queued 的设备留在队列里，sent/offline 的旧记录没人清：设备离线时
        #   排过旧版本 A，之后上线收到新版本 B 并应用成功，队列里的 A 仍然在，
        #   30s 巡检会把 A 重新投下去 —— 设备发现 A≠当前版本，于是下载并应用 A，
        #   屏幕从新图**退回旧图**。用户看到的就是"我下发了新壁纸，设备却还是旧的/
        #   干脆没反应"。sent 表示本次已投递（新版本已经到达设备），offline 表示本机
        #   明确送不到（由 device_config 兜底），两种情况都不该再补投旧版本。
        for device_id in sent + offline:
            await self._dequeue(device_id)
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
