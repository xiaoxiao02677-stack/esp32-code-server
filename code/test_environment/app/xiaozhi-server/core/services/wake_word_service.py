#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唤醒词推送服务"""
import asyncio
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WakeWordService:
    """唤醒词管理服务，作为单例挂在 WebSocketServer 上。"""

    def __init__(self):
        self._connections: Dict[str, object] = {}
        self._agent_devices: Dict[str, set] = {}
        self._offline_queue: Dict[str, List[dict]] = {}
        self._lock = asyncio.Lock()
        # 心跳服务引用：由 app.py 注入。心跳在线=设备可达（WS 可能未建），
        # 在线设备列表 = WS 连接 ∪ 心跳在线，供推送调度页展示真实可达设备。
        self.heartbeat_server = None
        logger.info("WakeWordService 初始化完成")

    def set_heartbeat_server(self, heartbeat_server) -> None:
        self.heartbeat_server = heartbeat_server

    async def register_connection(self, device_id: str, conn: object) -> None:
        async with self._lock:
            self._connections[device_id] = conn
            pending = self._offline_queue.pop(device_id, [])
        if pending:
            # 对齐推送策略：未绑定设备、MQTT 网关设备不下发
            if getattr(conn, "need_bind", False) or getattr(conn, "conn_from_mqtt_gateway", False):
                logger.info(f"设备 {device_id} 未绑定或来自MQTT网关，丢弃 {len(pending)} 条离线唤醒词")
                return
            logger.info(f"设备 {device_id} 上线，尝试下发 {len(pending)} 条离线唤醒词")
            failed = []
            for msg in pending:
                if not await self._push_to_conn(device_id, conn, msg):
                    failed.append(msg)
            if failed:
                # 发送失败的重新入队，等待下次上线或重试
                async with self._lock:
                    self._offline_queue.setdefault(device_id, []).extend(failed)

    async def unregister_connection(self, device_id: str) -> None:
        async with self._lock:
            self._connections.pop(device_id, None)

    def register_agent_device(self, agent_id: str, device_id: str) -> None:
        if agent_id not in self._agent_devices:
            self._agent_devices[agent_id] = set()
        self._agent_devices[agent_id].add(device_id)
        logger.debug(f"设备 {device_id} 绑定到 agent {agent_id}")

    async def push_wake_words(self, agent_id: Optional[str], device_id: Optional[str], wake_words: List[str], tts_rate: int = 0) -> dict:
        """推送唤醒词到目标设备（在线直推 / 离线缓存）。

        设备端消息固件 application.cc 只认 device_config 等 10 种 type，
        wake_word 消息会被静默丢弃；因此对在线设备改发：
        {"type":"device_config","payload":{"wake_word":[词1,词2,...]}}
        → board.cc ApplyDeviceConfig → MultiNet UpdateWakeWordCommands 热更新。
        空数组配合固件 ClearWakeWordCommands 语义可清空唤醒词。
        """
        wake_words = [str(w) for w in wake_words if w]
        msg = {
            "type": "device_config",
            "payload": {"wake_word": wake_words},
        }
        result = {"sent": 0, "offline": 0, "failed": 0, "skipped": 0}
        target_ids: set = set()
        if agent_id and agent_id in self._agent_devices:
            target_ids |= self._agent_devices[agent_id]
        if device_id:
            target_ids.add(device_id)
        if not target_ids:
            logger.warning(f"无目标设备可推送: agent_id={agent_id}, device_id={device_id}")
            return result
        async with self._lock:
            snapshot = dict(self._connections)
        offline_updates: Dict[str, List[dict]] = {}
        for did in target_ids:
            conn = snapshot.get(did)
            if conn is not None:
                # 对齐 connection.py 云端配置下发策略：未绑定设备、MQTT 网关设备不下发
                if getattr(conn, "need_bind", False) or getattr(conn, "conn_from_mqtt_gateway", False):
                    logger.info(f"设备 {did} 未绑定或来自MQTT网关，跳过唤醒词推送")
                    result["skipped"] += 1
                    continue
                ok = await self._push_to_conn(did, conn, msg)
                if ok:
                    # 同步服务端匹配词表（helloHandle/文本匹配用），推送热更新后无需重连
                    try:
                        conn.config["wakeup_words"] = list(wake_words)
                    except Exception:
                        pass
                    result["sent"] += 1
                else:
                    result["failed"] += 1
            else:
                # 配置语义：离线队列每设备只保留最新一条，避免历史堆积
                offline_updates[did] = [msg]
                result["offline"] += 1
        if offline_updates:
            async with self._lock:
                self._offline_queue.update(offline_updates)
            logger.info(f"唤醒词已缓存至 {len(offline_updates)} 个离线设备")
        return result

    def get_online_devices(self) -> List[str]:
        """在线设备 = WS 连接中的设备 ∪ 心跳在线的设备。

        固件 2.5.x 起心跳常驻、WS 按需建立：设备心跳在线但 WS 已断时，
        单看 WS 会误判离线（推送调度页显示 0 台在线）。合并两个来源，
        心跳在线代表设备网络可达，可与推送目标选择共用。
        """
        online = set(self._connections.keys())
        hb = getattr(self, "heartbeat_server", None)
        if hb is not None:
            try:
                for device_id, info in hb.devices.items():
                    if not info.get("online"):
                        continue
                    # 心跳上报 ID 形如 xiaozhi-14c19fd13348（前缀+无冒号MAC），
                    # WS/设备库用 14:c1:9f:d1:33:48 冒号格式；归一化后合并，
                    # 保证推送目标与 WS 连接键一致。
                    normalized = str(device_id)
                    if normalized.startswith("xiaozhi-") and ":" not in normalized:
                        raw = normalized[len("xiaozhi-"):].lower()
                        if len(raw) == 12 and all(c in "0123456789abcdef" for c in raw):
                            normalized = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
                    online.add(normalized)
            except Exception as e:
                logger.warning(f"合并心跳在线设备失败: {e}")
        return list(online)

    async def _push_to_conn(self, device_id: str, conn: object, msg: dict) -> bool:
        try:
            if not hasattr(conn, "websocket") or conn.websocket is None:
                logger.warning(f"设备 {device_id} 的 websocket 为 None，跳过推送")
                return False
            ws = conn.websocket
            closed = False
            if hasattr(ws, "closed") and ws.closed:
                closed = True
            elif hasattr(ws, "state") and ws.state.name == "CLOSED":
                closed = True
            if closed:
                logger.warning(f"设备 {device_id} 连接已关闭，跳过推送")
                return False
            await ws.send(json.dumps(msg))
            logger.info(f"向设备 {device_id} 推送唤醒词")
            return True
        except Exception as e:
            logger.error(f"向设备 {device_id} 推送唤醒词失败: {e}")
            return False
