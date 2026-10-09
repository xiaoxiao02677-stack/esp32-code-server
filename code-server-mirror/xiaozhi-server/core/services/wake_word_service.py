"""唤醒词推送服务。

功能：
- 维护 device_id -> ConnectionHandler 的活跃连接映射。
- 支持按 agent_id 向所有绑定该 agent 的在线设备推送唤醒词。
- 支持离线存储：设备离线时缓存唤醒词，下次连接成功后自动下发。
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WakeWordService:
    """唤醒词管理服务，作为单例挂在 WebSocketServer 上。"""

    def __init__(self):
        # device_id -> ConnectionHandler（在线连接）
        self._connections: Dict[str, object] = {}
        # agent_id -> set(device_id)，由 ConnectionHandler 在 _background_initialize 完成后回调注册
        self._agent_devices: Dict[str, set] = {}
        # device_id -> List[dict]，离线时缓存待下发的唤醒词消息
        self._offline_queue: Dict[str, List[dict]] = {}
        self._lock = asyncio.Lock()
        logger.info("WakeWordService 初始化完成")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def register_connection(self, device_id: str, conn: object) -> None:
        """注册一个在线连接。若设备有离线缓存，立即尝试下发。"""
        async with self._lock:
            self._connections[device_id] = conn
            # 触发离线缓存下发
            pending = self._offline_queue.pop(device_id, [])
        if pending:
            logger.info(
                f"设备 {device_id} 上线，尝试下发 {len(pending)} 条离线唤醒词"
            )
            for msg in pending:
                await self._push_to_conn(device_id, conn, msg)

    async def unregister_connection(self, device_id: str) -> None:
        """移除在线连接，将未送达的消息回收到离线队列。"""
        async with self._lock:
            self._connections.pop(device_id, None)

    def register_agent_device(self, agent_id: str, device_id: str) -> None:
        """设备绑定完成（agent_id 已知）后调用。"""
        if agent_id not in self._agent_devices:
            self._agent_devices[agent_id] = set()
        self._agent_devices[agent_id].add(device_id)
        logger.debug(f"设备 {device_id} 绑定到 agent {agent_id}")

    async def push_wake_words(
        self,
        agent_id: Optional[str],
        device_id: Optional[str],
        wake_words: List[str],
        tts_rate: int = 0,
    ) -> dict:
        """
        下发唤醒词列表。

        Args:
            agent_id: 若指定，向该 agent 下所有绑定设备推送；
                      否则只能按 device_id 单个推送。
            device_id: 若指定，仅向该设备推送（与 agent_id 可叠加）。
            wake_words: 唤醒词列表，如 ["你好小智", "Hi XiaoZhi"]。
            tts_rate: TTS 语速，默认 0（正常）。

        Returns:
            {"sent": int, "offline": int, "failed": int}
        """
        if not wake_words:
            return {"sent": 0, "offline": 0, "failed": 0}

        msg = {
            "type": "wake_word",
            "wake_words": wake_words,
            "tts_rate": tts_rate,
        }
        result = {"sent": 0, "offline": 0, "failed": 0}

        # 确定目标设备集合
        target_ids: set = set()
        if agent_id and agent_id in self._agent_devices:
            target_ids |= self._agent_devices[agent_id]
        if device_id:
            target_ids.add(device_id)

        if not target_ids:
            logger.warning(f"无目标设备可推送唤醒词: agent_id={agent_id}, device_id={device_id}")
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
                # 设备离线，缓存到离线队列
                offline_snapshot.setdefault(did, []).append(msg)
                result["offline"] += 1

        # 更新离线队列
        if result["offline"] > 0:
            async with self._lock:
                for did, msgs in offline_snapshot.items():
                    existing = self._offline_queue.get(did, [])
                    existing.extend(msgs)
                    self._offline_queue[did] = existing
                logger.info(
                    f"唤醒词已缓存至 {len(offline_snapshot)} 个离线设备"
                )

        return result

    # ------------------------------------------------------------------
    # 查询接口（供 HTTP API 使用）
    # ------------------------------------------------------------------

    def get_online_devices(self) -> List[str]:
        """返回当前所有在线设备的 device_id 列表。"""
        return list(self._connections.keys())

    def get_device_connections(self) -> Dict[str, object]:
        """返回 device_id -> ConnectionHandler 的映射副本。"""
        return dict(self._connections)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _push_to_conn(
        self, device_id: str, conn: object, msg: dict
    ) -> bool:
        """向单个 ConnectionHandler 推送消息，失败时记录日志并返回 False。"""
        try:
            if not hasattr(conn, "websocket") or conn.websocket is None:
                logger.warning(f"设备 {device_id} 的 websocket 为 None，跳过推送")
                return False
            # 安全地检查连接状态
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
            logger.info(f"向设备 {device_id} 推送唤醒词: {msg['wake_words']}")
            return True
        except Exception as e:
            logger.error(f"向设备 {device_id} 推送唤醒词失败: {e}")
            return False
