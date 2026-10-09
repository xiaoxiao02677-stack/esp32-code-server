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
        logger.info("WakeWordService 初始化完成")

    async def register_connection(self, device_id: str, conn: object) -> None:
        async with self._lock:
            self._connections[device_id] = conn
            pending = self._offline_queue.pop(device_id, [])
        if pending:
            logger.info(f"设备 {device_id} 上线，尝试下发 {len(pending)} 条离线唤醒词")
            for msg in pending:
                await self._push_to_conn(device_id, conn, msg)

    async def unregister_connection(self, device_id: str) -> None:
        async with self._lock:
            self._connections.pop(device_id, None)

    def register_agent_device(self, agent_id: str, device_id: str) -> None:
        if agent_id not in self._agent_devices:
            self._agent_devices[agent_id] = set()
        self._agent_devices[agent_id].add(device_id)
        logger.debug(f"设备 {device_id} 绑定到 agent {agent_id}")

    async def push_wake_words(self, agent_id: Optional[str], device_id: Optional[str], wake_words: List[str], tts_rate: int = 0) -> dict:
        if not wake_words:
            return {"sent": 0, "offline": 0, "failed": 0}
        msg = {"type": "wake_word", "wake_words": wake_words, "tts_rate": tts_rate}
        result = {"sent": 0, "offline": 0, "failed": 0}
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
            offline_snapshot = dict(self._offline_queue)
        for did in target_ids:
            conn = snapshot.get(did)
            if conn is not None:
                ok = await self._push_to_conn(did, conn, msg)
                if ok:
                    result["sent"] += 1
                else:
                    result["failed"] += 1
            else:
                offline_snapshot.setdefault(did, []).append(msg)
                result["offline"] += 1
        if result["offline"] > 0:
            async with self._lock:
                for did, msgs in offline_snapshot.items():
                    existing = self._offline_queue.get(did, [])
                    existing.extend(msgs)
                    self._offline_queue[did] = existing
                logger.info(f"唤醒词已缓存至 {len(offline_snapshot)} 个离线设备")
        return result

    def get_online_devices(self) -> List[str]:
        return list(self._connections.keys())

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
